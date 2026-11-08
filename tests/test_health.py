from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import AdminUser, Inquiry, MediaAsset, User
from app.seed import seed_content
from app.routes.admin import configure_cloudinary
import cloudinary


class PortfolioApiTests(unittest.TestCase):
    def setUp(self):
        self.upload_directory = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret-key-with-at-least-32-bytes",
            "JWT_SECRET_KEY": "test-jwt-secret-key-with-at-least-32-bytes",
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
            "FRONTEND_ORIGINS": [frontend_origin],
            "UPLOAD_FOLDER": self.upload_directory.name,
        })
        response = app.test_client().options(
            "/api/inquiries",
            headers={
                "Origin": frontend_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.headers.get("Access-Control-Allow-Origin"), frontend_origin)
        self.assertEqual(response.headers.get("Access-Control-Allow-Credentials"), "true")

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

    def test_public_registration_rejects_invalid_details(self):
        response = self.client.post("/api/auth/register", json={
            "name": "Test Account",
            "email": "not-an-email",
            "password": "short",
        })
        self.assertEqual(response.status_code, 400)

    def test_admin_routes_require_login_and_accept_hashed_admin(self):
        response = self.client.get("/api/admin/overview")
        self.assertEqual(response.status_code, 401)

        admin = AdminUser(email="admin@example.com")
        admin.set_password("not-a-real-password-123")
        db.session.add(admin)
        db.session.commit()

        login = self.client.post("/api/auth/login", json={
            "email": "ADMIN@example.com",
            "password": "not-a-real-password-123",
        })
        self.assertEqual(login.status_code, 200)
        self.assertIn("csrf_token", login.json)

        overview = self.client.get("/api/admin/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json["total_projects"], 0)
        self.assertEqual(overview.json["total_inquiries"], 0)

        csrf_header = {"X-CSRF-TOKEN": login.json["csrf_token"]}
        created = self.client.post("/api/admin/projects", json={
            "name": "Verified project",
            "category": "Web Applications",
            "description": "A project supplied by the administrator.",
            "technologies": ["React", "Flask"],
            "published": True,
        }, headers=csrf_header)
        self.assertEqual(created.status_code, 201)

        public_projects = self.client.get("/api/portfolio").json["projects"]
        self.assertEqual([project["name"] for project in public_projects], ["Verified project"])

        replaced = self.client.put(f"/api/admin/projects/{created.json['id']}", json={
            "cover_image": "https://res.cloudinary.com/test/image/upload/replacement.webp",
        }, headers=csrf_header)
        self.assertEqual(replaced.status_code, 200)
        self.assertEqual(replaced.json["cover_image"], "https://res.cloudinary.com/test/image/upload/replacement.webp")
        self.assertEqual(replaced.json["description"], "A project supplied by the administrator.")

        deleted = self.client.delete(f"/api/admin/projects/{created.json['id']}", headers=csrf_header)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/portfolio").json["projects"], [])

    def test_admin_service_pricing_contact_and_inquiry_updates_persist(self):
        admin = AdminUser(email="content@example.com")
        admin.set_password("not-a-real-password-654")
        db.session.add(admin)
        inquiry = Inquiry(
            name="Test Contact",
            email="contact@example.com",
            service="Website Development",
            message="A test inquiry.",
        )
        db.session.add(inquiry)
        db.session.commit()
        login = self.client.post("/api/auth/login", json={
            "email": admin.email,
            "password": "not-a-real-password-654",
        })
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

        profile = self.client.put("/api/admin/profile", json={
            "name": "Mabrixel",
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

        admin = AdminUser(email="uploads@example.com")
        admin.set_password("not-a-real-password-456")
        db.session.add(admin)
        db.session.commit()
        login = self.client.post("/api/auth/login", json={
            "email": admin.email,
            "password": "not-a-real-password-456",
        })
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
            "USE_CLOUDINARY": True,
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
            "CLOUDINARY_FOLDER": "mabrixel",
        })
        admin = AdminUser(email="cloudinary@example.com")
        admin.set_password("not-a-real-password-789")
        db.session.add(admin)
        db.session.commit()
        login = self.client.post("/api/auth/login", json={
            "email": admin.email,
            "password": "not-a-real-password-789",
        })
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

    def test_admin_provision_command_is_idempotent_and_does_not_replace_password(self):
        runner = self.app.test_cli_runner()
        environment = {
            "INITIAL_ADMIN_EMAIL": "ian@gmail.com",
            "INITIAL_ADMIN_PASSWORD": "initial-provisioning-password",
        }
        with patch.dict("os.environ", environment):
            first = runner.invoke(args=["provision-admin"])
            self.assertEqual(first.exit_code, 0, first.output)
            admin = AdminUser.query.filter_by(email="ian@gmail.com").one()
            admin.set_password("rotated-admin-password")
            db.session.commit()

            second = runner.invoke(args=["provision-admin"])

        self.assertEqual(second.exit_code, 0, second.output)
        self.assertEqual(AdminUser.query.filter_by(email="ian@gmail.com").count(), 1)
        self.assertTrue(admin.check_password("rotated-admin-password"))


if __name__ == "__main__":
    unittest.main()