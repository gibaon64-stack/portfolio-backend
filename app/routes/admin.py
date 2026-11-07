from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import AdminUser, Inquiry, JourneyEntry, Profile, Project, Service, SocialLink


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
        if not db.session.get(AdminUser, int(get_jwt_identity())):
            return jsonify({"error": "Administrator account is unavailable."}), 401
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
    from urllib.parse import urlparse

    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc) and not parsed.username


def string_list(value, field, *, maximum=40, item_limit=180):
    if not isinstance(value, list) or len(value) > maximum:
        return None, (jsonify({"error": f"{field} must be a list of at most {maximum} items."}), 400)
    clean_values = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > item_limit:
            return None, (jsonify({"error": f"Each {field} item must be text up to {item_limit} characters."}), 400)
        clean_values.append(item.strip())
    return clean_values, None


def save_entity(entity, fields):
    payload, error = json_payload()
    if error:
        return error

    for key, settings in fields.items():
        if key not in payload:
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

    for key in ("published", "active"):
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
        "introduction": {"limit": 5000},
        "hero_description": {"limit": 1000},
        "photo_url": {"limit": 500, "url": True, "optional": True},
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
    status = payload.get("status")
    if status not in INQUIRY_STATUSES:
        return jsonify({"error": "Choose pending, contacted, or completed."}), 400
    inquiry = db.get_or_404(Inquiry, inquiry_id)
    inquiry.status = status
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

    try:
        image = Image.open(image_file.stream)
        image_format = image.format
        width, height = image.size
        if image_format not in ALLOWED_IMAGE_FORMATS or width > 6000 or height > 6000 or width * height > 30_000_000:
            return jsonify({"error": "Upload a JPEG, PNG, or WebP image up to 6,000 px per side."}), 400
        image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return jsonify({"error": "The uploaded file is not a valid supported image."}), 400

    filename = f"{uuid4().hex}{ALLOWED_IMAGE_FORMATS[image_format]}"
    image_file.stream.seek(0)
    stored_image = Image.open(image_file.stream)
    stored_image.save(Path(current_app.config["UPLOAD_FOLDER"]) / filename, format=image_format)
    return jsonify({"url": f"/api/uploads/{filename}"}), 201


@admin_routes.get("/uploads/<path:filename>")
def get_uploaded_image(filename):
    if Path(filename).name != filename:
        return jsonify({"error": "Invalid image path."}), 400
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename, max_age=86400)