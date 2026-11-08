from functools import wraps
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from cloudinary.exceptions import AuthorizationRequired, Error as CloudinaryError
from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.admin_auth import admin_identity_matches, configured_admin_credentials
from app.extensions import db
from app.models import Inquiry, JourneyEntry, MediaAsset, Profile, Project, Service, SocialLink


admin_routes = Blueprint("admin", __name__, url_prefix="/api")
ALLOWED_IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
PROJECT_CATEGORIES = {
    "Website Development",
    "Web Applications",
    "Mobile Applications",
    "Business Software",
    "Custom Software Solutions",
}
INQUIRY_STATUSES = {"pending", "contacted", "completed"}


def admin_required(view):
    @wraps(view)
    @jwt_required()
    def wrapped(*args, **kwargs):
        if get_jwt().get("role") != "admin":
            return jsonify({"error": "Administrator access is required."}), 403
        if configured_admin_credentials() is None:
            return jsonify({"error": "Administrator authentication is not configured."}), 503
        if not admin_identity_matches(get_jwt_identity()):
            return jsonify({"error": "Administrator access is required."}), 403
        return view(*args, **kwargs)

    return wrapped


def json_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "Submit a JSON object."}), 400)
    return payload, None


def bounded_text(payload, key, *, required=False, limit=5000, optional=False):
    if key not in payload and not required:
        return None, None
    raw = payload.get(key)
    if raw is None and optional:
        return None, None
    if not isinstance(raw, str):
        return None, (jsonify({"error": f"{key} must be text."}), 400)
    value = raw.strip()
    if required and not value:
        return None, (jsonify({"error": f"{key} is required."}), 400)
    if len(value) > limit:
        return None, (jsonify({"error": f"{key} must be at most {limit} characters."}), 400)
    return value or None, None


def valid_url(value):
    if value in (None, ""):
        return True
    if not isinstance(value, str) or len(value) > 1000:
        return False
    if any(character.isspace() for character in value):
        return False
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(hostname)
        and parsed.username is None
        and parsed.password is None
    )


def string_list(value, field, *, maximum=40, item_limit=180):
    if not isinstance(value, list) or len(value) > maximum:
        return None, (jsonify({"error": f"{field} must be a list of at most {maximum} items."}), 400)
    clean_values = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > item_limit:
            return None, (jsonify({"error": f"Each {field} item must be text up to {item_limit} characters."}), 400)
        clean_values.append(item.strip())
    return clean_values, None


def service_pricing(value):
    if not isinstance(value, dict):
        return None, (jsonify({"error": "pricing must be a JSON object."}), 400)
    allowed_keys = {
        "startingPrice",
        "estimatedRange",
        "pricingModel",
        "timeline",
        "deliverables",
        "stages",
        "optionalAddOns",
        "packages",
    }
    if set(value) - allowed_keys:
        return None, (jsonify({"error": "pricing contains an unsupported field."}), 400)
    for key, limit in (("estimatedRange", 100), ("pricingModel", 100), ("timeline", 120)):
        if key in value and (not isinstance(value[key], str) or len(value[key]) > limit):
            return None, (jsonify({"error": f"pricing.{key} must be text up to {limit} characters."}), 400)
    if "startingPrice" in value and (
        not isinstance(value["startingPrice"], int)
        or isinstance(value["startingPrice"], bool)
        or value["startingPrice"] < 0
    ):
        return None, (jsonify({"error": "pricing.startingPrice must be a non-negative integer."}), 400)
    for key in ("deliverables", "optionalAddOns"):
        if key in value:
            items, error = string_list(value[key], f"pricing.{key}", maximum=40, item_limit=180)
            if error:
                return None, error
            value[key] = items
    if "stages" in value:
        stages = value["stages"]
        if not isinstance(stages, list) or len(stages) > 40:
            return None, (jsonify({"error": "pricing.stages must be a list of at most 40 items."}), 400)
        normalized_stages = []
        for stage in stages:
            if (
                not isinstance(stage, dict)
                or not isinstance(stage.get("name"), str)
                or not stage["name"].strip()
                or len(stage["name"]) > 180
                or not isinstance(stage.get("cost"), int)
                or isinstance(stage.get("cost"), bool)
                or stage["cost"] < 0
            ):
                return None, (jsonify({"error": "Each pricing stage needs a name and a non-negative integer cost."}), 400)
            normalized_stages.append({"name": stage["name"].strip(), "cost": stage["cost"]})
        value["stages"] = normalized_stages
    if "packages" in value:
        packages = value["packages"]
        expected_prices = {"BRONZE": 12000, "SILVER": 16000, "GOLD": 22000}
        if not isinstance(packages, list) or len(packages) > len(expected_prices):
            return None, (jsonify({"error": "pricing.packages must contain at most three packages."}), 400)
        normalized_packages = []
        seen_names = set()
        for package in packages:
            if not isinstance(package, dict):
                return None, (jsonify({"error": "Each pricing package must be an object."}), 400)
            allowed_package_keys = {
                "name",
                "price",
                "description",
                "included_services",
                "platform_count",
                "content_details",
                "management_details",
            }
            if set(package) - allowed_package_keys:
                return None, (jsonify({"error": "A pricing package contains an unsupported field."}), 400)
            name = package.get("name")
            price = package.get("price")
            if (
                not isinstance(name, str)
                or name not in expected_prices
                or name in seen_names
                or not isinstance(price, int)
                or isinstance(price, bool)
                or price != expected_prices.get(name)
            ):
                return None, (jsonify({"error": "Use the BRONZE, SILVER, and GOLD names with their configured prices."}), 400)
            description = package.get("description", "")
            if not isinstance(description, str) or len(description) > 500:
                return None, (jsonify({"error": "Package descriptions must be text up to 500 characters."}), 400)
            included_services, error = string_list(
                package.get("included_services", []),
                "pricing.packages.included_services",
                maximum=30,
                item_limit=180,
            )
            if error:
                return None, error
            platform_count = package.get("platform_count")
            if platform_count is not None and (
                not isinstance(platform_count, int)
                or isinstance(platform_count, bool)
                or not 1 <= platform_count <= 100
            ):
                return None, (jsonify({"error": "Package platform_count must be a positive integer or null."}), 400)
            details = {}
            for key in ("content_details", "management_details"):
                item = package.get(key, "")
                if not isinstance(item, str) or len(item) > 1000:
                    return None, (jsonify({"error": f"Package {key} must be text up to 1,000 characters."}), 400)
                details[key] = item.strip()
            normalized_packages.append({
                "name": name,
                "price": price,
                "description": description.strip(),
                "included_services": included_services,
                "platform_count": platform_count,
                **details,
            })
            seen_names.add(name)
        value["packages"] = normalized_packages
    return value, None


def configure_cloudinary():
    if not current_app.config.get("USE_CLOUDINARY") and not current_app.config.get("CLOUDINARY_REQUIRED"):
        return False

    cloudinary_url = current_app.config.get("CLOUDINARY_URL")
    if cloudinary_url:
        parsed = urlparse(cloudinary_url)
        if (
            parsed.scheme != "cloudinary"
            or not parsed.hostname
            or not parsed.username
            or not parsed.password
        ):
            return False
        config = {
            "cloud_name": parsed.hostname,
            "api_key": unquote(parsed.username),
            "api_secret": unquote(parsed.password),
            "secure": True,
        }
        if parsed.path.strip("/"):
            config["private_cdn"] = True
            config["secure_distribution"] = parsed.path.strip("/")
        cloudinary.config(**config)
        return True

    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME")
    api_key = current_app.config.get("CLOUDINARY_API_KEY")
    api_secret = current_app.config.get("CLOUDINARY_API_SECRET")

    if not all([cloud_name, api_key, api_secret]):
        return False

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )
    return True


def upload_to_cloudinary(image_file, folder):
    if not configure_cloudinary():
        return None, None, None

    try:
        result = cloudinary.uploader.upload(
            image_file,
            folder=folder,
            resource_type="image",
            allowed_formats=["jpg", "jpeg", "png", "webp"],
            transformation=[{"quality": "auto", "fetch_format": "auto"}],
        )
    except AuthorizationRequired:  # pragma: no cover - provider failure depends on credentials
        current_app.logger.error("Cloudinary rejected the server credentials.")
        return None, None, "Cloudinary rejected its server credentials. Check the Cloudinary cloud name, API key, and API secret."
    except CloudinaryError:  # pragma: no cover - provider failure depends on network credentials
        current_app.logger.error("Cloudinary image upload failed.")
        return None, None, "Cloudinary image upload failed."
    except OSError:  # pragma: no cover - provider failure depends on network
        current_app.logger.error("Cloudinary image upload could not reach the provider.")
        return None, None, "Could not connect to Cloudinary. Check the server network and try again."

    secure_url = result.get("secure_url") or result.get("url")
    public_id = result.get("public_id")
    if not isinstance(secure_url, str) or not secure_url.startswith("https://") or not isinstance(public_id, str):
        return None, None, "Cloudinary returned an invalid image response."
    return secure_url, public_id, None


def save_entity(entity, fields):
    payload, error = json_payload()
    if error:
        return error

    for key, settings in fields.items():
        if key not in payload:
            continue
        if settings.get("json") == "pricing":
            value, error = service_pricing(payload[key])
            if error:
                return error
            setattr(entity, key, value)
            continue
        if settings.get("json") == "list":
            value, error = string_list(payload[key], key, maximum=80, item_limit=500)
            if error:
                return error
            setattr(entity, key, value)
            continue
        value, error = bounded_text(
            payload,
            key,
            required=settings.get("required", False),
            limit=settings.get("limit", 5000),
            optional=settings.get("optional", False),
        )
        if error:
            return error
        if settings.get("url") and not valid_url(value):
            return jsonify({"error": f"{key} must be an http or https URL."}), 400
        setattr(entity, key, value)

    for key in ("technologies", "screenshots", "capabilities", "features"):
        if key in payload:
            value, error = string_list(payload[key], key)
            if error:
                return error
            setattr(entity, key, value)

    for key in ("published", "active", "featured"):
        if key in payload:
            if not isinstance(payload[key], bool):
                return jsonify({"error": f"{key} must be a boolean."}), 400
            setattr(entity, key, payload[key])

    if "position" in payload:
        if not isinstance(payload["position"], int) or payload["position"] < 0:
            return jsonify({"error": "position must be a non-negative integer."}), 400
        entity.position = payload["position"]

    return None


@admin_routes.get("/admin/overview")
@admin_required
def overview():
    return jsonify({
        "total_projects": Project.query.count(),
        "published_projects": Project.query.filter_by(published=True).count(),
        "total_services": Service.query.count(),
        "active_services": Service.query.filter_by(active=True).count(),
        "total_inquiries": Inquiry.query.count(),
        "recent_inquiries": [
            item.to_dict()
            for item in Inquiry.query.order_by(Inquiry.created_at.desc()).limit(5)
        ],
    })


@admin_routes.get("/admin/content")
@admin_required
def all_content():
    profile = Profile.query.first()
    return jsonify({
        "profile": profile.to_dict() if profile else None,
        "journey": [item.to_dict() for item in JourneyEntry.query.order_by(JourneyEntry.position, JourneyEntry.id)],
        "projects": [item.to_dict() for item in Project.query.order_by(Project.created_at.desc())],
        "services": [item.to_dict() for item in Service.query.order_by(Service.position, Service.id)],
        "social_links": [item.to_dict() for item in SocialLink.query.order_by(SocialLink.position, SocialLink.id)],
        "inquiries": [item.to_dict() for item in Inquiry.query.order_by(Inquiry.created_at.desc()).limit(200)],
        "media_assets": [item.to_dict() for item in MediaAsset.query.order_by(MediaAsset.created_at.desc()).limit(500)],
    })


@admin_routes.put("/admin/profile")
@admin_required
def update_profile():
    profile = Profile.query.first()
    if not profile:
        profile = Profile(name="Ian Mabruk")
        db.session.add(profile)
    error = save_entity(profile, {
        "name": {"required": True, "limit": 160},
        "professional_title": {"limit": 180},
        "introduction": {"limit": 5000},
        "skills": {"json": "list"},
        "experience": {"json": "list"},
        "education": {"json": "list"},
        "certifications": {"json": "list"},
        "hero_description": {"limit": 1000},
        "hero_image_url": {"limit": 500, "url": True, "optional": True},
        "about_intro": {"limit": 3000},
        "about_who_we_are": {"limit": 3000},
        "about_mission": {"limit": 3000},
        "about_what_we_do": {"limit": 3000},
        "about_approach": {"limit": 3000},
        "about_why_choose_us": {"limit": 3000},
        "photo_url": {"limit": 500, "url": True, "optional": True},
        "contact_image_url": {"limit": 500, "url": True, "optional": True},
        "location": {"limit": 160},
        "email": {"limit": 254},
        "phone": {"limit": 48},
    })
    if error:
        return error
    db.session.commit()
    return jsonify(profile.to_dict())


@admin_routes.route("/admin/journey", methods=["POST"])
@admin_required
def create_journey():
    entry = JourneyEntry(title="", description="")
    error = save_entity(entry, {
        "title": {"required": True, "limit": 180},
        "period": {"limit": 120},
        "description": {"required": True, "limit": 5000},
    })
    if error:
        return error
    db.session.add(entry)
    db.session.commit()
    return jsonify(entry.to_dict()), 201


@admin_routes.put("/admin/journey/<int:entry_id>")
@admin_required
def update_journey(entry_id):
    entry = db.get_or_404(JourneyEntry, entry_id)
    error = save_entity(entry, {
        "title": {"required": True, "limit": 180},
        "period": {"limit": 120},
        "description": {"required": True, "limit": 5000},
    })
    if error:
        return error
    db.session.commit()
    return jsonify(entry.to_dict())


@admin_routes.delete("/admin/journey/<int:entry_id>")
@admin_required
def delete_journey(entry_id):
    db.session.delete(db.get_or_404(JourneyEntry, entry_id))
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_routes.post("/admin/projects")
@admin_required
def create_project():
    project = Project(name="", category="", description="")
    error = save_entity(project, {
        "name": {"required": True, "limit": 180},
        "category": {"required": True, "limit": 80},
        "description": {"required": True, "limit": 5000},
        "detailed_description": {"limit": 10000, "optional": True},
        "status": {"limit": 80},
        "cover_image": {"limit": 500, "url": True, "optional": True},
        "challenges": {"limit": 3000, "optional": True},
        "solutions": {"limit": 3000, "optional": True},
        "live_url": {"limit": 1000, "url": True, "optional": True},
        "github_url": {"limit": 1000, "url": True, "optional": True},
    })
    if error:
        return error
    if project.category not in PROJECT_CATEGORIES:
        return jsonify({"error": "Choose a supported project category."}), 400
    db.session.add(project)
    db.session.commit()
    return jsonify(project.to_dict()), 201


@admin_routes.put("/admin/projects/<int:project_id>")
@admin_required
def update_project(project_id):
    project = db.get_or_404(Project, project_id)
    error = save_entity(project, {
        "name": {"required": True, "limit": 180},
        "category": {"required": True, "limit": 80},
        "description": {"required": True, "limit": 5000},
        "detailed_description": {"limit": 10000, "optional": True},
        "status": {"limit": 80},
        "cover_image": {"limit": 500, "url": True, "optional": True},
        "challenges": {"limit": 3000, "optional": True},
        "solutions": {"limit": 3000, "optional": True},
        "live_url": {"limit": 1000, "url": True, "optional": True},
        "github_url": {"limit": 1000, "url": True, "optional": True},
    })
    if error:
        return error
    if project.category not in PROJECT_CATEGORIES:
        return jsonify({"error": "Choose a supported project category."}), 400
    db.session.commit()
    return jsonify(project.to_dict())


@admin_routes.delete("/admin/projects/<int:project_id>")
@admin_required
def delete_project(project_id):
    db.session.delete(db.get_or_404(Project, project_id))
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_routes.post("/admin/services")
@admin_required
def create_service():
    service = Service(title="", description="")
    error = save_entity(service, {
        "title": {"required": True, "limit": 180},
        "description": {"required": True, "limit": 3000},
        "image_url": {"limit": 500, "url": True, "optional": True},
        "pricing": {"json": "pricing"},
    })
    if error:
        return error
    db.session.add(service)
    db.session.commit()
    return jsonify(service.to_dict()), 201


@admin_routes.put("/admin/services/<int:service_id>")
@admin_required
def update_service(service_id):
    service = db.get_or_404(Service, service_id)
    error = save_entity(service, {
        "title": {"required": True, "limit": 180},
        "description": {"required": True, "limit": 3000},
        "image_url": {"limit": 500, "url": True, "optional": True},
        "pricing": {"json": "pricing"},
    })
    if error:
        return error
    db.session.commit()
    return jsonify(service.to_dict())


@admin_routes.delete("/admin/services/<int:service_id>")
@admin_required
def delete_service(service_id):
    db.session.delete(db.get_or_404(Service, service_id))
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_routes.post("/admin/social-links")
@admin_required
def create_social_link():
    payload, error = json_payload()
    if error:
        return error
    platform, error = bounded_text(payload, "platform", required=True, limit=80)
    if error:
        return error
    url, error = bounded_text(payload, "url", required=True, limit=1000)
    if error:
        return error
    if not valid_url(url):
        return jsonify({"error": "Social links must be http or https URLs."}), 400
    link = SocialLink(platform=platform, url=url)
    error = save_entity(link, {})
    if error:
        return error
    db.session.add(link)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "A social link for that platform already exists."}), 409
    return jsonify(link.to_dict()), 201


@admin_routes.put("/admin/social-links/<int:link_id>")
@admin_required
def update_social_link(link_id):
    link = db.get_or_404(SocialLink, link_id)
    payload, error = json_payload()
    if error:
        return error
    for key, limit in (("platform", 80), ("url", 1000)):
        if key in payload:
            value, error = bounded_text(payload, key, required=True, limit=limit)
            if error:
                return error
            if key == "url" and not valid_url(value):
                return jsonify({"error": "Social links must be http or https URLs."}), 400
            setattr(link, key, value)
    error = save_entity(link, {})
    if error:
        return error
    db.session.commit()
    return jsonify(link.to_dict())


@admin_routes.delete("/admin/social-links/<int:link_id>")
@admin_required
def delete_social_link(link_id):
    db.session.delete(db.get_or_404(SocialLink, link_id))
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_routes.patch("/admin/inquiries/<int:inquiry_id>")
@admin_required
def update_inquiry(inquiry_id):
    payload, error = json_payload()
    if error:
        return error
    inquiry = db.get_or_404(Inquiry, inquiry_id)
    if "status" in payload:
        status = payload["status"]
        if not isinstance(status, str) or status not in INQUIRY_STATUSES:
            return jsonify({"error": "Choose pending, contacted, or completed."}), 400
        inquiry.status = status
    if "internal_notes" in payload:
        notes = payload["internal_notes"]
        if not isinstance(notes, str) or len(notes) > 5000:
            return jsonify({"error": "Internal notes must be text up to 5,000 characters."}), 400
        inquiry.internal_notes = notes.strip()
    if "status" not in payload and "internal_notes" not in payload:
        return jsonify({"error": "Provide a status or internal_notes update."}), 400
    db.session.commit()
    return jsonify(inquiry.to_dict())


@admin_routes.delete("/admin/inquiries/<int:inquiry_id>")
@admin_required
def delete_inquiry(inquiry_id):
    db.session.delete(db.get_or_404(Inquiry, inquiry_id))
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_routes.post("/admin/uploads")
@admin_required
def upload_image():
    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        return jsonify({"error": "Choose an image file."}), 400
    if not Path(secure_filename(image_file.filename)).suffix:
        return jsonify({"error": "Image files must have a filename extension."}), 400
    allowed_mimetypes = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
    expected_format = allowed_mimetypes.get(image_file.mimetype)
    if not expected_format:
        return jsonify({"error": "Upload a JPEG, PNG, or WebP image."}), 400

    try:
        image = Image.open(image_file.stream)
        image_format = image.format
        width, height = image.size
        if image_format != expected_format or width > 6000 or height > 6000 or width * height > 30_000_000:
            return jsonify({"error": "Upload a JPEG, PNG, or WebP image up to 6,000 px per side."}), 400
        image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return jsonify({"error": "The uploaded file is not a valid supported image."}), 400

    contexts = {"projects", "services", "about", "contact", "homepage"}
    context = request.form.get("context", "homepage")
    if context not in contexts:
        return jsonify({"error": "Choose a supported image context."}), 400
    base_folder = (current_app.config.get("CLOUDINARY_FOLDER") or "mabrixel").strip("/")
    folder = f"{base_folder}/{context}"

    cloudinary_enabled = (
        current_app.config.get("USE_CLOUDINARY")
        or current_app.config.get("CLOUDINARY_REQUIRED")
        or context == "about"
    )
    if cloudinary_enabled:
        if not configure_cloudinary():
            return jsonify({
                "error": "Profile images require Cloudinary. Configure CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET on the backend.",
            }), 503
        image_file.stream.seek(0)
        secure_url, public_id, cloudinary_error = upload_to_cloudinary(image_file.stream, folder)
        if cloudinary_error:
            return jsonify({"error": cloudinary_error}), 502
        asset = MediaAsset(public_id=public_id, secure_url=secure_url, folder=folder)
        db.session.add(asset)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "Cloudinary returned an image identifier already in use."}), 502
        return jsonify({"url": secure_url, "asset_id": public_id}), 201

    filename = f"{uuid4().hex}{ALLOWED_IMAGE_FORMATS[image_format]}"
    image_file.stream.seek(0)
    stored_image = Image.open(image_file.stream)
    stored_image.save(Path(current_app.config["UPLOAD_FOLDER"]) / filename, format=image_format)
    return jsonify({"url": f"/api/uploads/{filename}"}), 201


@admin_routes.delete("/admin/uploads/<int:asset_id>")
@admin_required
def delete_uploaded_image(asset_id):
    asset = db.get_or_404(MediaAsset, asset_id)
    if not configure_cloudinary():
        return jsonify({"error": "Cloudinary is not configured for image deletion."}), 503
    try:
        result = cloudinary.uploader.destroy(asset.public_id, resource_type=asset.resource_type)
    except CloudinaryError:  # pragma: no cover - provider failure depends on network credentials
        current_app.logger.error("Cloudinary image deletion failed.")
        return jsonify({"error": "Cloudinary image deletion failed."}), 502
    if result.get("result") != "ok":
        return jsonify({"error": "Cloudinary did not confirm image deletion."}), 502
    db.session.delete(asset)
    db.session.commit()
    return jsonify({"status": "deleted"})


@admin_routes.get("/uploads/<path:filename>")
def get_uploaded_image(filename):
    if Path(filename).name != filename:
        return jsonify({"error": "Invalid image path."}), 400
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, max_age=86400)