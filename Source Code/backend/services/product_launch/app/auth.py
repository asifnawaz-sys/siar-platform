"""Admin authentication and CSRF protection.

Admin uses a simple session login (username + password from config/env). The
password may be provided as a Werkzeug hash (``ADMIN_PASSWORD_HASH``) or, for
convenience in development, as plaintext (``ADMIN_PASSWORD``).

CSRF: admin state-changing requests carry a session-bound token in the
``X-CSRF-Token`` header (or a ``csrf_token`` form field). The public client API
is *not* cookie-authenticated — access is gated solely by the secret launch
token in the URL — so it is not vulnerable to CSRF and is exempt.
"""
from __future__ import annotations

import secrets
from functools import wraps

from flask import current_app, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash


def verify_credentials(username: str, password: str) -> bool:
    cfg = current_app.config
    if username != cfg["ADMIN_USERNAME"]:
        return False
    hashed = cfg.get("ADMIN_PASSWORD_HASH")
    if hashed:
        return check_password_hash(hashed, password)
    # Constant-time compare for the plaintext fallback.
    return secrets.compare_digest(password, cfg.get("ADMIN_PASSWORD", ""))


def login_admin() -> None:
    session["is_admin"] = True
    session.permanent = True
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)


def logout_admin() -> None:
    session.pop("is_admin", None)
    session.pop("csrf_token", None)


def is_admin() -> bool:
    return bool(session.get("is_admin"))


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def admin_required(view):
    """Protect admin *pages* — redirect to login when signed out."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def admin_api_required(view):
    """Protect admin *API/JSON* endpoints — 401 + CSRF check for writes."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify({"error": "Authentication required."}), 401
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
                return jsonify({"error": "Invalid or missing CSRF token."}), 403
        return view(*args, **kwargs)

    return wrapper
