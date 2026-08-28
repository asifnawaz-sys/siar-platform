from flask import Blueprint
from .routes import integrations_bp

def init_integrations_service(app):
    app.register_blueprint(integrations_bp, url_prefix='/api/integrations')
