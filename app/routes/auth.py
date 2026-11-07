from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_csrf_token,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)

from app.extensions import limiter
from app.models import AdminUser, db


auth_routes = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_routes.post("/login")
@limiter.limit("5 per 15 minutes")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Enter your administrator credentials."}), 400

    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    admin = AdminUser.query.filter_by(email=email).first()
    if not admin or not isinstance(password, str) or not admin.check_password(password):
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


@auth_routes.get("/me")
@jwt_required()
def current_user():
    admin = db.session.get(AdminUser, int(get_jwt_identity()))
    if not admin:
        return jsonify({"error": "Administrator account is unavailable."}), 401
    return jsonify({"user": {"id": admin.id, "email": admin.email, "role": admin.role}})


@auth_routes.post("/logout")
@jwt_required()
def logout():
    response = jsonify({"status": "ok"})
    unset_jwt_cookies(response)
    return response