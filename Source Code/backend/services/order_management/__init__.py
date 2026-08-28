from flask import Blueprint
from .routes import order_bp

def init_order_service(app):
    app.register_blueprint(order_bp, url_prefix='/api/orders')
