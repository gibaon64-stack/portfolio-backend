from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta
import secrets
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
from PIL import Image
from cloudinary.exceptions import AuthorizationRequired

from app import create_app
from app.extensions import db
from app.models import Inquiry, MediaAsset, Service, User
from app.seed import seed_content
from app.routes.admin import configure_cloudinary
import cloudinary


class PortfolioApiTests(unittest.TestCase):
    def setUp(self):
        self.upload_directory = tempfile.TemporaryDirectory()
        self.admin_email = f"{secrets.token_hex(8)}@example.test"
        self.admin_password = secrets.token_urlsafe(24)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-with-at-least-32-bytes",
            "JWT_SECRET_KEY": "test-jwt-secret-key-with-at-least-32-bytes",
            "INITIAL_ADMIN_EMAIL": self.admin_email,
            "INITIAL_ADMIN_PASSWORD": self.admin_password,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "JWT_COOKIE_SECURE": False,
            "RATELIMIT_ENABLED": False,
            "UPLOAD_FOLDER": self.upload_directory.name,
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        self.upload_directory.cleanup()

    def login_admin(self, email=None, password=None):
        return self.client.post("/api/auth/login", json={
            "email": self.admin_email if email is None else email,
            "password": self.admin_password if password is None else password,
        })

    def test_health_route_returns_ok(self):
        response = self.client.get(
            "/api/health",
            headers={"Origin": "http://localhost:5173"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            "http://localhost:5173",
        )

    def test_netlify_origin_is_allowed_for_cross_origin_api_requests(self):
        frontend_origin = "https://portfolio-mabrixel.netlify.app"
        app = create_app({
            "TESTING": True,
            "SECRET_KEY": "cors-test-secret-key-with-at-least-32-bytes",
            "JWT_SECRET_KEY": "cors-test-jwt-secret-key-with-at-least-32-bytes",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "UPLOAD_FOLDER": self.upload_directory.name,
        })
        response = app.test_client().options(
            "/api/inquiries",
            headers={
                "Origin": frontend_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            },
        )
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), frontend_origin)
        self.assertEqual(response.headers.get("Access-Control-Allow-Credentials"), "true")
        self.assertIn("idempotency-key", response.headers.get("Access-Control-Allow-Headers", "").lower())

    def test_seeded_public_content_uses_user_supplied_services(self):
        seed_content()
        response = self.client.get("/api/portfolio")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["profile"]["name"], "Ian Mabruk")
        self.assertEqual(len(response.json["journey"]), 6)
        self.assertEqual(
            [service["title"] for service in response.json["services"]],
            [
                "Software Engineering",
                "Website Development",
                "Mobile Application Development",
                "Digital Marketing",
            ],
        )
        marketing = next(service for service in response.json["services"] if service["title"] == "Digital Marketing")
        self.assertEqual(
            [(package["name"], package["price"]) for package in marketing["pricing"]["packages"]],
            [("BRONZE", 12000), ("SILVER", 16000), ("GOLD", 22000)],
        )
        marketing["pricing"]["packages"][0]["description"] = "Customized bronze package."
        marketing_service = Service.query.filter_by(title="Digital Marketing").one()
        marketing_service.pricing = marketing["pricing"]
        db.session.commit()
        seed_content()
        self.assertEqual(
            Service.query.filter_by(title="Digital Marketing").one().pricing["packages"][0]["description"],
            "Customized bronze package.",
        )
        self.assertEqual(response.json["projects"], [])
        self.assertEqual(response.json["social_links"], [])

    def test_inquiry_validation_and_persistence(self):
        invalid = self.client.post("/api/inquiries", json={"name": "Test", "email": "bad"})
        self.assertEqual(invalid.status_code, 400)

        response = self.client.post("/api/inquiries", json={
            "name": "A Client",
            "email": "CLIENT@example.com",
            "phone": "",
            "business_name": "Example Studio",
            "service": "Website Development",
            "budget": "",
            "timeline": "Next month",
            "message": "I would like to discuss a business website.",
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Inquiry.query.count(), 1)
        self.assertEqual(Inquiry.query.first().email, "client@example.com")
        self.assertEqual(Inquiry.query.first().business_name, "Example Studio")
        self.assertEqual(Inquiry.query.first().timeline, "Next month")

    def test_consultation_validation_persistence_and_idempotency(self):
        consultation_date = (datetime.now(ZoneInfo("Africa/Nairobi")) + timedelta(days=2)).date().isoformat()
        payload = {
            "name": "A Client",
            "email": "client@example.com",
            "phone": "+254 700 000 000",
            "business_name": "Example Studio",
            "service": "E-commerce Websites",
            "message": "I need an online store.",
            "consultation_date": consultation_date,
            "consultation_time": "14:30",
            "additional_requirements": "Connect the product inventory.",
        }
        headers = {"Idempotency-Key": "consultation-test-001"}
        response = self.client.post("/api/inquiries", json=payload, headers=headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Inquiry.query.count(), 1)
        saved = Inquiry.query.one()
        self.assertEqual(saved.consultation_date.isoformat(), consultation_date)
        self.assertEqual(saved.consultation_time, "14:30")
        self.assertEqual(saved.additional_requirements, "Connect the product inventory.")

        duplicate = self.client.post("/api/inquiries", json=payload, headers=headers)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json["id"], response.json["id"])
        self.assertEqual(Inquiry.query.count(), 1)

        payload["consultation_date"] = "2000-01-01"
        invalid_date = self.client.post(
            "/api/inquiries",
            json=payload,
            headers={"Idempotency-Key": "consultation-test-002"},
        )
        self.assertEqual(invalid_date.status_code, 400)
        self.assertEqual(Inquiry.query.count(), 1)

    def test_public_registration_hashes_password_and_duplicate_is_rejected(self):
        registration = {
            "name": "Test Account",
            "email": "TEST-USER@example.com",
            "password": "a-secure-test-password",
        }
        created = self.client.post("/api/auth/register", json=registration)
        self.assertEqual(created.status_code, 201)
        user = User.query.one()
        self.assertEqual(user.email, "test-user@example.com")
        self.assertEqual(user.role, "user")
        self.assertNotEqual(user.password_hash, registration["password"])
        self.assertTrue(user.check_password(registration["password"]))
        self.assertNotIn("password_hash", created.json["user"])

        duplicate = self.client.post("/api/auth/register", json=registration)
        self.assertEqual(duplicate.status_code, 409)

        login = self.client.post("/api/auth/user/login", json={
            "email": registration["email"],
            "password": registration["password"],
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json["user"]["role"], "user")
        self.assertEqual(self.client.get("/api/auth/user/me").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 403)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 403)
        admin_login = self.client.post("/api/auth/login", json=registration)
        self.assertEqual(admin_login.status_code, 401)

    def test_public_registration_rejects_invalid_details(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Test Account",
            "email": "not-an-email",
            "password": "short",
        })
        self.assertEqual(response.status_code, 400)

    def test_admin_login_uses_only_configured_credentials_and_protects_routes(self):
        response = self.client.get("/api/admin/overview")
        self.assertEqual(response.status_code, 401)

        wrong_password = self.login_admin(password=secrets.token_urlsafe(24))
        self.assertEqual(wrong_password.status_code, 401)

        wrong_email = self.login_admin(email=f"{secrets.token_hex(8)}@example.test")
        self.assertEqual(wrong_email.status_code, 401)

        login = self.login_admin()
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json["user"]["email"], self.admin_email)
        self.assertEqual(login.json["user"]["role"], "admin")
        self.assertIn("csrf_token", login.json)

        current_admin = self.client.get("/api/auth/me")
        self.assertEqual(current_admin.status_code, 200)
        self.assertEqual(current_admin.json["user"]["email"], self.admin_email)

        overview = self.client.get("/api/admin/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json["total_projects"], 0)
        self.assertEqual(overview.json["total_inquiries"], 0)

        csrf_header = {"X-CSRF-TOKEN": login.json["csrf_token"]}
        created = self.client.post("/api/admin/projects", json={
            "name": "Verified project",
            "category": "Web Applications",
            "description": "A project supplied by the administrator.",
            "detailed_description": "Detailed project information.",
            "technologies": ["React", "Flask"],
            "live_url": "https://example.com/projects/verified",
            "github_url": "https://github.com/example/verified",
            "featured": True,
            "published": True,
        }, headers=csrf_header)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json["detailed_description"], "Detailed project information.")
        self.assertTrue(created.json["featured"])
        self.assertEqual(created.json["live_url"], "https://example.com/projects/verified")

        draft = self.client.post("/api/admin/projects", json={
            "name": "Unpublished project",
            "category": "Web Applications",
            "description": "A draft should not be public.",
            "published": False,
        }, headers=csrf_header)
        self.assertEqual(draft.status_code, 201)
        public_projects = self.client.get("/api/portfolio").json["projects"]
        self.assertEqual([project["name"] for project in public_projects], ["Verified project"])
        self.assertEqual(public_projects[0]["live_url"], "https://example.com/projects/verified")
        self.assertTrue(public_projects[0]["featured"])
        self.assertEqual(public_projects[0]["detailed_description"], "Detailed project information.")

        replaced = self.client.put(f"/api/admin/projects/{created.json['id']}", json={
            "cover_image": "https://res.cloudinary.com/test/image/upload/replacement.webp",
        }, headers=csrf_header)
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(replaced.json["cover_image"], "https://res.cloudinary.com/test/image/upload/replacement.webp")
        self.assertEqual(replaced.json["description"], "A project supplied by the administrator.")
        self.assertEqual(replaced.json["live_url"], "https://example.com/projects/verified")

        invalid_url = self.client.put(f"/api/admin/projects/{created.json['id']}", json={
            "live_url": "https://example.com/a path",
        }, headers=csrf_header)
        self.assertEqual(invalid_url.status_code, 400)

        deleted = self.client.delete(f"/api/admin/projects/{created.json['id']}", headers=csrf_header)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/portfolio").json["projects"], [])
        self.assertEqual(self.client.delete(f"/api/admin/projects/{draft.json['id']}", headers=csrf_header).status_code, 200)

        logout = self.client.post("/api/auth/logout", headers=csrf_header)
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 401)

    def test_admin_login_and_protected_routes_reject_missing_environment_credentials(self):
        self.app.config["INITIAL_ADMIN_PASSWORD"] = None

        login = self.login_admin()
        self.assertEqual(login.status_code, 503)
        self.assertNotIn(self.admin_password, login.get_data(as_text=True))
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 401)

        self.app.config["INITIAL_ADMIN_PASSWORD"] = self.admin_password
        successful_login = self.login_admin()
        self.assertEqual(successful_login.status_code, 200)
        self.app.config["INITIAL_ADMIN_EMAIL"] = None
        protected = self.client.get("/api/admin/overview")
        self.assertEqual(protected.status_code, 503)
        self.assertNotIn(self.admin_password, protected.get_data(as_text=True))

    def test_admin_service_pricing_contact_and_inquiry_updates_persist(self):
        inquiry = Inquiry(
            name="Test Contact",
            email="contact@example.com",
            service="Website Development",
            message="A test inquiry.",
        )
        db.session.add(inquiry)
        db.session.commit()
        login = self.login_admin()
        csrf_header = {"X-CSRF-TOKEN": login.json["csrf_token"]}

        service = self.client.post("/api/admin/services", json={
            "title": "Website Development",
            "description": "Business websites.",
            "pricing": {
                "startingPrice": 85000,
                "estimatedRange": "KES 85,000 - 450,000",
                "pricingModel": "Project estimate",
                "timeline": "4 - 8 weeks",
                "stages": [{"name": "Design", "cost": 25000}],
            },
        }, headers=csrf_header)
        self.assertEqual(service.status_code, 201)
        self.assertEqual(self.client.get("/api/portfolio").json["services"][0]["pricing"]["startingPrice"], 85000)

        packages = [
            {"name": "BRONZE", "price": 12000, "description": "Bronze scope", "included_services": [], "platform_count": None, "content_details": "", "management_details": ""},
            {"name": "SILVER", "price": 16000, "description": "Silver scope", "included_services": ["Campaign planning"], "platform_count": 2, "content_details": "To be agreed", "management_details": "To be agreed"},
            {"name": "GOLD", "price": 22000, "description": "Gold scope", "included_services": [], "platform_count": 3, "content_details": "", "management_details": ""},
        ]
        package_update = self.client.put(f"/api/admin/services/{service.json['id']}", json={
            "pricing": {"packages": packages},
        }, headers=csrf_header)
        self.assertEqual(package_update.status_code, 200)
        self.assertEqual(
            [package["price"] for package in package_update.json["pricing"]["packages"]],
            [12000, 16000, 22000],
        )

        invalid_packages = [dict(packages[0], price=16000)]
        invalid_package_update = self.client.put(f"/api/admin/services/{service.json['id']}", json={
            "pricing": {"packages": invalid_packages},
        }, headers=csrf_header)
        self.assertEqual(invalid_package_update.status_code, 400)

        profile = self.client.put("/api/admin/profile", json={
            "name": "Mabrixel",
            "professional_title": "Software Engineer",
            "skills": ["React", "Flask"],
            "experience": ["Founder at Mabrixel Technologies"],
            "education": ["Software Engineering"],
            "certifications": ["Certification supplied by profile owner"],
            "email": "hello@example.com",
            "phone": "+254700000000",
            "location": "Kenya",
            "about_intro": "An editable company introduction.",
            "about_mission": "Editable mission copy.",
        }, headers=csrf_header)
        self.assertEqual(profile.status_code, 200)
        public_content = self.client.get("/api/portfolio").json
        self.assertEqual(public_content["contact"]["email"], "hello@example.com")
        self.assertEqual(public_content["profile"]["about_intro"], "An editable company introduction.")
        self.assertEqual(public_content["profile"]["professional_title"], "Software Engineer")
        self.assertEqual(public_content["profile"]["skills"], ["React", "Flask"])
        self.assertEqual(public_content["profile"]["experience"], ["Founder at Mabrixel Technologies"])

        updated = self.client.patch(f"/api/admin/inquiries/{inquiry.id}", json={
            "status": "contacted",
            "internal_notes": "Follow up next week.",
        }, headers=csrf_header)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["internal_notes"], "Follow up next week.")
        self.assertEqual(db.session.get(Inquiry, inquiry.id).status, "contacted")

    def test_upload_and_social_urls_are_validated(self):
        unauthorized = self.client.post("/api/admin/uploads")
        self.assertEqual(unauthorized.status_code, 401)

        login = self.login_admin()
        csrf_header = {"X-CSRF-TOKEN": login.json["csrf_token"]}

        invalid_image = self.client.post(
            "/api/admin/uploads",
            data={"image": (BytesIO(b"not an image"), "not-image.png")},
            headers=csrf_header,
        )
        self.assertEqual(invalid_image.status_code, 400)

        image_buffer = BytesIO()
        Image.new("RGB", (8, 8), color="black").save(image_buffer, format="PNG")
        image_buffer.seek(0)
        uploaded = self.client.post(
            "/api/admin/uploads",
            data={"image": (image_buffer, "profile.png")},
            headers=csrf_header,
        )
        self.assertEqual(uploaded.status_code, 201)
        self.assertTrue(Path(self.upload_directory.name, uploaded.json["url"].rsplit("/", 1)[-1]).exists())

        unsafe_link = self.client.post("/api/admin/social-links", json={
            "platform": "Portfolio",
            "url": "javascript:alert(1)",
        }, headers=csrf_header)
        self.assertEqual(unsafe_link.status_code, 400)

    def test_cloudinary_upload_saves_secure_asset_reference(self):
        self.app.config.update({
            "USE_CLOUDINARY": False,
            "CLOUDINARY_REQUIRED": True,
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
            "CLOUDINARY_FOLDER": "mabrixel",
        })
        login = self.login_admin()
        csrf_header = {"X-CSRF-TOKEN": login.json["csrf_token"]}

        image_buffer = BytesIO()
        Image.new("RGB", (8, 8), color="blue").save(image_buffer, format="PNG")
        image_buffer.seek(0)
        with patch("app.routes.admin.cloudinary.uploader.upload", return_value={
            "secure_url": "https://res.cloudinary.com/test-cloud/image/upload/test.png",
            "public_id": "mabrixel/projects/test",
        }) as cloudinary_upload:
            response = self.client.post(
                "/api/admin/uploads",
                data={"image": (image_buffer, "project.png"), "context": "projects"},
                headers=csrf_header,
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json["url"].startswith("https://"))
        self.assertEqual(response.json["asset_id"], "mabrixel/projects/test")
        self.assertEqual(MediaAsset.query.one().folder, "mabrixel/projects")
        cloudinary_upload.assert_called_once()
        with patch("app.routes.admin.cloudinary.uploader.destroy", return_value={"result": "ok"}) as cloudinary_destroy:
            deleted = self.client.delete(
                f"/api/admin/uploads/{MediaAsset.query.one().id}",
                headers=csrf_header,
            )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(MediaAsset.query.count(), 0)
        cloudinary_destroy.assert_called_once()

    def test_cloudinary_url_configuration_is_parsed_by_the_sdk(self):
        self.app.config.update({
            "USE_CLOUDINARY": True,
            "CLOUDINARY_URL": "cloudinary://test-key:test-secret@test-cloud",
            "CLOUDINARY_CLOUD_NAME": None,
            "CLOUDINARY_API_KEY": None,
            "CLOUDINARY_API_SECRET": None,
        })
        with self.app.app_context():
            self.assertTrue(configure_cloudinary())
        self.assertEqual(cloudinary.config().cloud_name, "test-cloud")

    def test_cloudinary_required_overrides_disabled_use_flag(self):
        self.app.config.update({
            "USE_CLOUDINARY": False,
            "CLOUDINARY_REQUIRED": True,
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
        })
        with self.app.app_context():
            self.assertTrue(configure_cloudinary())

    def test_cloudinary_authorization_error_is_actionable(self):
        self.app.config.update({
            "USE_CLOUDINARY": True,
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
        })
        login = self.login_admin()
        headers = {"X-CSRF-TOKEN": login.json["csrf_token"]}
        image_buffer = BytesIO()
        Image.new("RGB", (8, 8), color="blue").save(image_buffer, format="PNG")
        image_buffer.seek(0)
        with patch(
            "app.routes.admin.cloudinary.uploader.upload",
            side_effect=AuthorizationRequired("credentials rejected"),
        ):
            response = self.client.post(
                "/api/admin/uploads",
                data={"image": (image_buffer, "profile.png"), "context": "projects"},
                headers=headers,
            )
        self.assertEqual(response.status_code, 502)
        self.assertIn("rejected its server credentials", response.json["error"])
        self.assertNotIn("credentials rejected", response.json["error"])

    def test_profile_upload_falls_back_to_local_storage_without_cloudinary(self):
        self.app.config.update({
            "USE_CLOUDINARY": True,
            "CLOUDINARY_REQUIRED": False,
            "CLOUDINARY_CLOUD_NAME": None,
            "CLOUDINARY_API_KEY": None,
            "CLOUDINARY_API_SECRET": None,
        })
        login = self.login_admin()
        headers = {"X-CSRF-TOKEN": login.json["csrf_token"]}
        image_buffer = BytesIO()
        Image.new("RGB", (8, 8), color="green").save(image_buffer, format="PNG")
        image_buffer.seek(0)
        response = self.client.post(
            "/api/admin/uploads",
            data={"image": (image_buffer, "profile.png"), "context": "about"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json["url"].startswith("/api/uploads/"))
        self.assertTrue(Path(self.upload_directory.name, response.json["url"].rsplit("/", 1)[-1]).exists())
        self.assertEqual(MediaAsset.query.count(), 0)

    def test_required_cloudinary_reports_missing_configuration(self):
        self.app.config.update({
            "USE_CLOUDINARY": False,
            "CLOUDINARY_REQUIRED": True,
            "CLOUDINARY_CLOUD_NAME": None,
            "CLOUDINARY_API_KEY": None,
            "CLOUDINARY_API_SECRET": None,
        })
        login = self.login_admin()
        headers = {"X-CSRF-TOKEN": login.json["csrf_token"]}
        image_buffer = BytesIO()
        Image.new("RGB", (8, 8), color="green").save(image_buffer, format="PNG")
        image_buffer.seek(0)
        response = self.client.post(
            "/api/admin/uploads",
            data={"image": (image_buffer, "profile.png"), "context": "about"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("Cloudinary is required", response.json["error"])
        self.assertEqual(MediaAsset.query.count(), 0)

    def test_profile_photo_url_persists_and_is_returned_publicly(self):
        login = self.login_admin()
        headers = {"X-CSRF-TOKEN": login.json["csrf_token"]}
        photo_url = "https://res.cloudinary.com/test-cloud/image/upload/profile.webp"
        saved = self.client.put(
            "/api/admin/profile",
            json={"name": "Test Profile", "photo_url": photo_url},
            headers=headers,
        )
        self.assertEqual(saved.status_code, 200)
        public = self.client.get("/api/portfolio")
        self.assertEqual(public.json["profile"]["photo_url"], photo_url)

    def test_assistant_requires_server_key_and_uses_gemini_sdk(self):
        self.assertFalse(self.client.get("/api/assistant/status").json["available"])
        missing_key = self.client.post("/api/assistant/chat", json={"message": "What services do you offer?"})
        self.assertEqual(missing_key.status_code, 503)

        self.app.config["GEMINI_API_KEY"] = "test-gemini-key"
        self.app.config["GEMINI_MODEL"] = "test-model"
        self.assertTrue(self.client.get("/api/assistant/status").json["available"])
        seed_content()
        with patch("app.routes.assistant.genai.Client") as gemini_client:
            gemini_client.return_value.models.generate_content.return_value.text = "We offer software and website development."
            response = self.client.post("/api/assistant/chat", json={"message": "What services do you offer?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["reply"], "We offer software and website development.")
        gemini_client.assert_called_once_with(api_key="test-gemini-key")
        self.assertEqual(
            gemini_client.return_value.models.generate_content.call_args.kwargs["model"],
            "test-model",
        )

    def test_assistant_network_errors_do_not_expose_provider_details(self):
        self.app.config["GEMINI_API_KEY"] = "test-gemini-key"
        with patch("app.routes.assistant.genai.Client") as gemini_client:
            gemini_client.return_value.models.generate_content.side_effect = httpx.ConnectError("private connection detail")
            response = self.client.post("/api/assistant/chat", json={"message": "Can I start a project?"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("Could not connect", response.json["error"])
        self.assertNotIn("private connection detail", response.json["error"])


if __name__ == "__main__":
    unittest.main()