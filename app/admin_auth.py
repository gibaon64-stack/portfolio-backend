import secrets

from flask import current_app


def configured_admin_credentials():
    email = current_app.config.get("INITIAL_ADMIN_EMAIL")
    password = current_app.config.get("INITIAL_ADMIN_PASSWORD")
    if not isinstance(email, str) or not email.strip():
        return None
    if not isinstance(password, str) or not password:
        return None
    return email.strip().lower(), password


def constant_time_equal(left, right):
    return secrets.compare_digest(
        left.encode("utf-8", "surrogatepass"),
        right.encode("utf-8", "surrogatepass"),
    )


def admin_identity_matches(identity):
    credentials = configured_admin_credentials()
    return (
        credentials is not None
        and isinstance(identity, str)
        and constant_time_equal(identity, credentials[0])
    )
