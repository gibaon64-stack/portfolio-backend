import os
import secrets
from pathlib import Path


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///portfolio.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_ACCESS_COOKIE_NAME = "mabrixel_access"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
    JWT_COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "Lax")
    JWT_ACCESS_TOKEN_EXPIRES = 1800
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    UPLOAD_FOLDER = os.getenv(
        "UPLOAD_FOLDER",
        str(Path(__file__).resolve().parents[1] / "instance" / "uploads"),
    )
    CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    USE_CLOUDINARY = os.getenv(
        "USE_CLOUDINARY",
        "1" if CLOUDINARY_URL or all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)) else "0",
    ) == "1"
    CLOUDINARY_REQUIRED = os.getenv("CLOUDINARY_REQUIRED", "1" if os.getenv("RENDER") else "0") == "1"
    CLOUDINARY_FOLDER = os.getenv("CLOUDINARY_FOLDER", "mabrixel")
    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    @staticmethod
    def normalize_database_url(url):
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url
