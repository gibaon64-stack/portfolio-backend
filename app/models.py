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


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="user")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email, "role": self.role}


class MediaAsset(db.Model):
    __tablename__ = "media_assets"

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(255), unique=True, nullable=False)
    secure_url = db.Column(db.String(1000), nullable=False)
    folder = db.Column(db.String(255), nullable=False)
    resource_type = db.Column(db.String(32), nullable=False, default="image")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "public_id": self.public_id,
            "secure_url": self.secure_url,
            "folder": self.folder,
            "resource_type": self.resource_type,
            "created_at": self.created_at.isoformat(),
        }


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, default="Ian Mabruk")
    professional_title = db.Column(db.String(180), nullable=False, default="")
    introduction = db.Column(db.Text, nullable=False, default="")
    skills = db.Column(db.JSON, nullable=True, default=list)
    technologies = db.Column(db.JSON, nullable=True, default=list)
    experience = db.Column(db.JSON, nullable=True, default=list)
    education = db.Column(db.JSON, nullable=True, default=list)
    certifications = db.Column(db.JSON, nullable=True, default=list)
    hero_description = db.Column(db.Text, nullable=False, default="")
    hero_image_url = db.Column(db.String(500))
    about_intro = db.Column(db.Text, nullable=False, default="")
    about_who_we_are = db.Column(db.Text, nullable=False, default="")
    about_mission = db.Column(db.Text, nullable=False, default="")
    about_what_we_do = db.Column(db.Text, nullable=False, default="")
    about_approach = db.Column(db.Text, nullable=False, default="")
    about_why_choose_us = db.Column(db.Text, nullable=False, default="")
    photo_url = db.Column(db.String(500))
    contact_image_url = db.Column(db.String(500))
    location = db.Column(db.String(160))
    email = db.Column(db.String(254))
    phone = db.Column(db.String(48))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "professional_title": self.professional_title,
            "introduction": self.introduction,
            "skills": self.skills or [],
            "technologies": self.technologies or [],
            "experience": self.experience or [],
            "education": self.education or [],
            "certifications": self.certifications or [],
            "hero_description": self.hero_description,
            "hero_image_url": self.hero_image_url,
            "about_intro": self.about_intro,
            "about_who_we_are": self.about_who_we_are,
            "about_mission": self.about_mission,
            "about_what_we_do": self.about_what_we_do,
            "about_approach": self.about_approach,
            "about_why_choose_us": self.about_why_choose_us,
            "photo_url": self.photo_url,
            "contact_image_url": self.contact_image_url,
            "location": self.location,
            "email": self.email,
            "phone": self.phone,
        }


class JourneyEntry(db.Model):
    __tablename__ = "journey_entries"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    period = db.Column(db.String(120))
    organization = db.Column(db.String(180))
    description = db.Column(db.Text, nullable=False)
    image_urls = db.Column(db.JSON, nullable=True, default=list)
    position = db.Column(db.Integer, nullable=False, default=0)
    published = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "period": self.period,
            "organization": self.organization,
            "description": self.description,
            "image_urls": self.image_urls or [],
            "position": self.position,
            "published": self.published,
        }


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    detailed_description = db.Column(db.Text)
    status = db.Column(db.String(80))
    cover_image = db.Column(db.String(500))
    features = db.Column(db.JSON, nullable=False, default=list)
    challenges = db.Column(db.Text)
    solutions = db.Column(db.Text)
    technologies = db.Column(db.JSON, nullable=False, default=list)
    screenshots = db.Column(db.JSON, nullable=False, default=list)
    live_url = db.Column(db.String(1000))
    github_url = db.Column(db.String(1000))
    position = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    published = db.Column(db.Boolean, nullable=False, default=False)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "detailed_description": self.detailed_description,
            "status": self.status,
            "cover_image": self.cover_image,
            "features": self.features or [],
            "challenges": self.challenges,
            "solutions": self.solutions,
            "technologies": self.technologies or [],
            "screenshots": self.screenshots or [],
            "live_url": self.live_url,
            "github_url": self.github_url,
            "position": self.position,
            "published": self.published,
            "featured": self.featured,
        }


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(500))
    capabilities = db.Column(db.JSON, nullable=False, default=list)
    pricing = db.Column(db.JSON, nullable=False, default=dict)
    position = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "image_url": self.image_url,
            "capabilities": self.capabilities or [],
            "pricing": self.pricing or {},
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
    business_name = db.Column(db.String(160))
    service = db.Column(db.String(180), nullable=False)
    budget = db.Column(db.String(80))
    timeline = db.Column(db.String(120))
    message = db.Column(db.Text, nullable=False)
    consultation_date = db.Column(db.Date)
    consultation_time = db.Column(db.String(5))
    additional_requirements = db.Column(db.Text)
    idempotency_key = db.Column(db.String(64), unique=True)
    status = db.Column(db.String(24), nullable=False, default="pending")
    internal_notes = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "business_name": self.business_name,
            "service": self.service,
            "budget": self.budget,
            "timeline": self.timeline,
            "message": self.message,
            "consultation_date": self.consultation_date.isoformat() if self.consultation_date else None,
            "consultation_time": self.consultation_time,
            "additional_requirements": self.additional_requirements,
            "status": self.status,
            "internal_notes": self.internal_notes,
            "created_at": self.created_at.isoformat(),
        }