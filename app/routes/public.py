import re

from flask import Blueprint, jsonify, request

from app.extensions import db, limiter
from app.models import Inquiry, JourneyEntry, Profile, Project, Service, SocialLink


public_routes = Blueprint("public", __name__, url_prefix="/api")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@public_routes.get("/portfolio")
def get_portfolio():
    profile = Profile.query.first()
    return jsonify({
        "profile": profile.to_dict() if profile else None,
        "contact": {
            "email": profile.email,
            "phone": profile.phone,
            "location": profile.location,
        } if profile else {},
        "journey": [
            item.to_dict()
            for item in JourneyEntry.query.filter_by(published=True).order_by(JourneyEntry.position, JourneyEntry.id)
        ],
        "projects": [
            item.to_dict()
            for item in Project.query.filter_by(published=True).order_by(Project.created_at.desc())
        ],
        "services": [
            item.to_dict()
            for item in Service.query.filter_by(active=True).order_by(Service.position, Service.id)
        ],
        "social_links": [
            item.to_dict()
            for item in SocialLink.query.filter_by(active=True).order_by(SocialLink.position, SocialLink.id)
        ],
    })


@public_routes.post("/inquiries")
@limiter.limit("5 per hour")
def create_inquiry():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Submit inquiry details as JSON."}), 400

    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    phone = str(payload.get("phone") or "").strip()
    business_name = str(payload.get("business_name") or "").strip()
    service = str(payload.get("service", "")).strip()
    budget = str(payload.get("budget") or "").strip()
    timeline = str(payload.get("timeline") or "").strip()
    message = str(payload.get("message", "")).strip()

    if not name or len(name) > 120:
        return jsonify({"error": "Enter a name between 1 and 120 characters."}), 400
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
        return jsonify({"error": "Enter a valid email address."}), 400
    if len(phone) > 40 or len(business_name) > 160 or len(service) > 180 or len(budget) > 80 or len(timeline) > 120:
        return jsonify({"error": "One or more inquiry fields exceed their allowed length."}), 400
    if not service or not message or len(message) > 5000:
        return jsonify({"error": "Choose a service and provide a message of at most 5,000 characters."}), 400

    inquiry = Inquiry(
        name=name,
        email=email,
        phone=phone or None,
        business_name=business_name or None,
        service=service,
        budget=budget or None,
        timeline=timeline or None,
        message=message,
    )
    db.session.add(inquiry)
    db.session.commit()
    return jsonify({"id": inquiry.id, "status": inquiry.status}), 201