import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.extensions import db, limiter
from app.models import Inquiry, JourneyEntry, Profile, Project, Service, SocialLink


public_routes = Blueprint("public", __name__, url_prefix="/api")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s().-]{6,24}$")
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
EAT = ZoneInfo("Africa/Nairobi")


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
    additional_requirements = str(payload.get("additional_requirements") or "").strip()
    consultation_date_value = payload.get("consultation_date")
    consultation_time_value = payload.get("consultation_time")
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()

    if not name or len(name) > 120:
        return jsonify({"error": "Enter a name between 1 and 120 characters."}), 400
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
        return jsonify({"error": "Enter a valid email address."}), 400
    if len(phone) > 40 or len(business_name) > 160 or len(service) > 180 or len(budget) > 80 or len(timeline) > 120:
        return jsonify({"error": "One or more inquiry fields exceed their allowed length."}), 400
    if not service or not message or len(message) > 5000:
        return jsonify({"error": "Choose a service and provide a message of at most 5,000 characters."}), 400
    if len(additional_requirements) > 5000:
        return jsonify({"error": "Additional requirements must be at most 5,000 characters."}), 400
    if idempotency_key and not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        return jsonify({"error": "The request identifier is invalid. Please try submitting again."}), 400

    consultation_date = None
    consultation_time = None
    if consultation_date_value is not None or consultation_time_value is not None:
        if not isinstance(consultation_date_value, str) or not isinstance(consultation_time_value, str):
            return jsonify({"error": "Choose a valid consultation date and time."}), 400
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", consultation_date_value) or not re.fullmatch(r"\d{2}:\d{2}", consultation_time_value):
            return jsonify({"error": "Choose a valid consultation date and time."}), 400
        try:
            consultation_date = date.fromisoformat(consultation_date_value)
            consultation_time = time.fromisoformat(consultation_time_value)
        except ValueError:
            return jsonify({"error": "Choose a valid consultation date and time."}), 400
        if consultation_time.second or consultation_time.microsecond:
            return jsonify({"error": "Choose a consultation time in 24-hour HH:MM format."}), 400
        consultation_datetime = datetime.combine(consultation_date, consultation_time, tzinfo=EAT)
        if consultation_datetime <= datetime.now(EAT):
            return jsonify({"error": "Choose a future consultation date and time in Africa/Nairobi time."}), 400
        if not PHONE_PATTERN.fullmatch(phone):
            return jsonify({"error": "Enter a valid phone number for the consultation."}), 400

    if idempotency_key:
        existing = Inquiry.query.filter_by(idempotency_key=idempotency_key).first()
        if existing:
            return jsonify({"id": existing.id, "status": existing.status}), 200

    inquiry = Inquiry(
        name=name,
        email=email,
        phone=phone or None,
        business_name=business_name or None,
        service=service,
        budget=budget or None,
        timeline=timeline or None,
        message=message,
        consultation_date=consultation_date,
        consultation_time=consultation_time.isoformat(timespec="minutes") if consultation_time else None,
        additional_requirements=additional_requirements or None,
        idempotency_key=idempotency_key or None,
    )
    db.session.add(inquiry)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if idempotency_key:
            existing = Inquiry.query.filter_by(idempotency_key=idempotency_key).first()
            if existing:
                return jsonify({"id": existing.id, "status": existing.status}), 200
        raise
    return jsonify({"id": inquiry.id, "status": inquiry.status}), 201