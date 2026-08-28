from flask import Blueprint
from .routes import shopify_bp

def init_shopify_service(app):
    app.register_blueprint(shopify_bp, url_prefix='/api/shopify')
