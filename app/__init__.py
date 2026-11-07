import os
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash

from app.config import Config
from app.extensions import db, jwt, limiter, migrate


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config["SQLALCHEMY_DATABASE_URI"] = Config.normalize_database_url(
        os.getenv("DATABASE_URL", app.config["SQLALCHEMY_DATABASE_URI"])
    )

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
        supports_credentials=True,
        allow_headers=["Content-Type", "X-CSRF-TOKEN"],
    )

    from app import models
    from app.routes.admin import admin_routes
    from app.routes.auth import auth_routes
    from app.routes.health import health_routes
    from app.routes.public import public_routes

    app.register_blueprint(health_routes)
    app.register_blueprint(public_routes)
    app.register_blueprint(auth_routes)
    app.register_blueprint(admin_routes)

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": "Request exceeds the 10 MB limit."}), 413

    @app.cli.command("init-db")
    def init_db_command():
        """Create local tables for a fresh SQLite database."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("seed-content")
    def seed_content_command():
        """Add the user-provided starter profile, journey, and services."""
        from app.seed import seed_content

        seed_content()
        click.echo("Starter content is ready.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin_command(email, password):
        """Create an administrator without exposing credentials to the public API."""
        from app.models import AdminUser

        normalized_email = email.strip().lower()
        if "@" not in normalized_email or len(normalized_email) > 254:
            raise click.ClickException("Enter a valid email address.")
        if len(password) < 12:
            raise click.ClickException("Use an administrator password with at least 12 characters.")
        if AdminUser.query.filter_by(email=normalized_email).first():
            raise click.ClickException("An administrator with that email already exists.")

        admin = AdminUser(email=normalized_email, password_hash=generate_password_hash(password))
        db.session.add(admin)
        db.session.commit()
        click.echo("Administrator account created.")

    return app