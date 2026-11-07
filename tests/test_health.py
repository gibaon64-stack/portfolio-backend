from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from app import create_app
from app.extensions import db
from app.models import AdminUser, Inquiry
from app.seed import seed_content


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
            "service": "Website Development",
            "budget": "",
            "message": "I would like to discuss a business website.",
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Inquiry.query.count(), 1)
        self.assertEqual(Inquiry.query.first().email, "client@example.com")

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

        deleted = self.client.delete(f"/api/admin/projects/{created.json['id']}", headers=csrf_header)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/portfolio").json["projects"], [])

    def test_upload_and_social_urls_are_validated(self):
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


if __name__ == "__main__":
    unittest.main()