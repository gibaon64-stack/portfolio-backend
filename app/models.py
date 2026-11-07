from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class AdminUser(db.Model):
    __tablename__ = "admin_users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="admin")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, default="Ian Mabruk")
    introduction = db.Column(db.Text, nullable=False, default="")
    hero_description = db.Column(db.Text, nullable=False, default="")
    photo_url = db.Column(db.String(500))
    location = db.Column(db.String(160))
    email = db.Column(db.String(254))
    phone = db.Column(db.String(48))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "introduction": self.introduction,
            "hero_description": self.hero_description,
            "photo_url": self.photo_url,
            "location": self.location,
            "email": self.email,
            "phone": self.phone,
        }


class JourneyEntry(db.Model):
    __tablename__ = "journey_entries"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    period = db.Column(db.String(120))
    description = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    published = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "period": self.period,
            "description": self.description,
            "position": self.position,
            "published": self.published,
        }


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(80))
    cover_image = db.Column(db.String(500))
    features = db.Column(db.JSON, nullable=False, default=list)
    challenges = db.Column(db.Text)
    solutions = db.Column(db.Text)
    technologies = db.Column(db.JSON, nullable=False, default=list)
    screenshots = db.Column(db.JSON, nullable=False, default=list)
    live_url = db.Column(db.String(1000))
    github_url = db.Column(db.String(1000))
    published = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "status": self.status,
            "cover_image": self.cover_image,
            "features": self.features or [],
            "challenges": self.challenges,
            "solutions": self.solutions,
            "technologies": self.technologies or [],
            "screenshots": self.screenshots or [],
            "live_url": self.live_url,
            "github_url": self.github_url,
            "published": self.published,
        }


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    capabilities = db.Column(db.JSON, nullable=False, default=list)
    position = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "capabilities": self.capabilities or [],
            "position": self.position,
            "active": self.active,
        }


class SocialLink(db.Model):
    __tablename__ = "social_links"

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(80), nullable=False, unique=True)
    url = db.Column(db.String(1000), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "platform": self.platform,
            "url": self.url,
            "position": self.position,
            "active": self.active,
        }


class Inquiry(db.Model):
    __tablename__ = "inquiries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False, index=True)
    phone = db.Column(db.String(40))
    service = db.Column(db.String(180), nullable=False)
    budget = db.Column(db.String(80))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "service": self.service,
            "budget": self.budget,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }