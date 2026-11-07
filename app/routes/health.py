from flask import Blueprint, jsonify


health_routes = Blueprint("health", __name__, url_prefix="/api")


@health_routes.get("/health")
def health_check():
    return jsonify({"status": "ok"})