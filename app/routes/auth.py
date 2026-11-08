import re
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_csrf_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from sqlalchemy.exc import IntegrityError

from app.extensions import limiter
from app.models import AdminUser, User, db


auth_routes = Blueprint("auth", __name__, url_prefix="/api/auth")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@auth_routes.post("/login")
@limiter.limit("5 per 15 minutes")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Enter your administrator credentials."}), 400

    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    admin = AdminUser.query.filter_by(email=email).first()
    if not admin or admin.role != "admin" or not isinstance(password, str) or not admin.check_password(password):
        return jsonify({"error": "Email or password is incorrect."}), 401

    access_token = create_access_token(
        identity=str(admin.id),
        additional_claims={"role": admin.role},
        expires_delta=timedelta(seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]),
    )
    response = jsonify({
        "user": {"id": admin.id, "email": admin.email, "role": admin.role},
        "csrf_token": get_csrf_token(access_token),
    })
    set_access_cookies(response, access_token)
    return response


@auth_routes.post("/register")
@limiter.limit("5 per hour")
def register():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Submit registration details as JSON."}), 400

    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        return jsonify({"error": "Enter a name between 1 and 120 characters."}), 400
    if not isinstance(email, str):
        return jsonify({"error": "Enter a valid email address."}), 400
    normalized_email = email.strip().lower()
    if len(normalized_email) > 254 or not EMAIL_PATTERN.fullmatch(normalized_email):
        return jsonify({"error": "Enter a valid email address."}), 400
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        return jsonify({"error": "Password must be between 12 and 128 characters."}), 400
    if User.query.filter_by(email=normalized_email).first():
        return jsonify({"error": "An account with that email already exists."}), 409

    user = User(name=name.strip(), email=normalized_email, role="user")
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "An account with that email already exists."}), 409
    return jsonify({"user": user.to_dict()}), 201


@auth_routes.post("/user/login")
@limiter.limit("5 per 15 minutes")
def login_user():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Enter your account credentials."}), 400

    email = payload.get("email")
    password = payload.get("password")
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    user = User.query.filter_by(email=normalized_email).first()
    if not user or not isinstance(password, str) or not user.check_password(password):
        return jsonify({"error": "Email or password is incorrect."}), 401

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": "user"},
        expires_delta=timedelta(seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]),
    )
    response = jsonify({
        "user": user.to_dict(),
        "csrf_token": get_csrf_token(access_token),
    })
    set_access_cookies(response, access_token)
    return response


@auth_routes.get("/me")
@jwt_required()
def current_user():
    if get_jwt().get("role") != "admin":
        return jsonify({"error": "Administrator access is required."}), 403
    admin = db.session.get(AdminUser, int(get_jwt_identity()))
    if not admin:
        return jsonify({"error": "Administrator account is unavailable."}), 401
    return jsonify({
        "user": {"id": admin.id, "email": admin.email, "role": admin.role},
        "csrf_token": get_jwt().get("csrf"),
    })


@auth_routes.get("/user/me")
@jwt_required()
def current_public_user():
    if get_jwt().get("role") != "user":
        return jsonify({"error": "User account access is required."}), 403
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "User account is unavailable."}), 401
    return jsonify({"user": user.to_dict(), "csrf_token": get_jwt().get("csrf")})


@auth_routes.post("/logout")
@jwt_required()
def logout():
    response = jsonify({"status": "ok"})
    unset_jwt_cookies(response)
    return response