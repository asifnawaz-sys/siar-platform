"""Application factory."""
from __future__ import annotations

from datetime import timedelta

from flask import Flask, jsonify

from .config import Config, INSTANCE_DIR
from .extensions import db


def create_app(config_object: type[Config] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object or Config)
    app.permanent_session_lifetime = timedelta(days=14)

    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    # Register blueprints
    from .blueprints.client import bp as client_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.api import bp as api_bp

    app.register_blueprint(client_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    # Make the CSRF token available to all templates.
    from . import auth

    @app.context_processor
    def inject_globals():
        return {"csrf_token": auth.csrf_token, "is_admin": auth.is_admin}

    # JSON error handlers for API routes; HTML routes fall through to Flask.
    @app.errorhandler(404)
    def not_found(err):
        from flask import request
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return ("<h1>404 — Not found</h1>", 404)

    @app.errorhandler(500)
    def server_error(err):
        from flask import request
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error."}), 500
        return ("<h1>500 — Something went wrong</h1>", 500)

    with app.app_context():
        db.create_all()

    return app
