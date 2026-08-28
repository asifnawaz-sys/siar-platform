"""SIAR Platform - Integrated Flask Application"""

import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, jsonify, session, send_file
from flask_cors import CORS
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'siar-platform-dev-key')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

CORS(app)
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'

# Authentication
VALID_USERS = {'admin': 'admin@SIAR123'}

def require_auth(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# Core Routes
@app.route('/')
def index():
    if 'user_id' in session:
        frontend_path = Path(__file__).parent.parent / 'frontend' / 'dashboard.html'
        return send_file(str(frontend_path)) if frontend_path.exists() else jsonify({'error': 'Dashboard not found'})
    return jsonify({'error': 'Please login'})

@app.route('/api/analytics/ui')
@require_auth
def analytics_ui():
    frontend_path = Path(__file__).parent.parent / 'frontend' / 'shopify_analytics.html'
    return send_file(str(frontend_path)) if frontend_path.exists() else jsonify({'error': 'Analytics UI not found'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if username in VALID_USERS and VALID_USERS[username] == password:
        session['user_id'] = username
        return jsonify({'success': True}), 200
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True}), 200

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'success': True, 'service': 'SIAR Platform', 'status': 'operational'}), 200

# Load service blueprints
try:
    from services.crm import crm_bp
    app.register_blueprint(crm_bp)
    logger.info("CRM service loaded")
except Exception as e:
    logger.warning(f"CRM service load failed: {e}")

try:
    from services.shopify_analytics import shopify_bp
    app.register_blueprint(shopify_bp, url_prefix='/api/shopify')
    logger.info("Shopify Analytics service loaded")
except Exception as e:
    logger.warning(f"Shopify Analytics service load failed: {e}")

try:
    from services.order_management import order_bp
    app.register_blueprint(order_bp, url_prefix='/api/orders')
    logger.info("Order Management service loaded")
except Exception as e:
    logger.warning(f"Order Management service load failed: {e}")

# Register Phase 5 blueprints
try:
    from services.core.user_routes import user_bp
    app.register_blueprint(user_bp, url_prefix='/api')
    logger.info("User Management service loaded")
except Exception as e:
    logger.warning(f"User Management service load failed: {e}")

try:
    from services.analytics.analytics_routes import analytics_bp
    app.register_blueprint(analytics_bp, url_prefix='/api')
    logger.info("Analytics service loaded")
except Exception as e:
    logger.warning(f"Analytics service load failed: {e}")

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(503)
def service_unavailable(error):
    logger.error(f"Service unavailable: {error}")
    return jsonify({'error': 'Service unavailable', 'status': 503}), 503

@app.errorhandler(504)
def gateway_timeout(error):
    logger.error(f"Gateway timeout: {error}")
    return jsonify({'error': 'Gateway timeout', 'status': 504}), 504

# Middleware for security headers
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

def create_app():
    return app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8765))
    logger.info(f"Starting SIAR Platform on port {port}")
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
