#!/usr/bin/env python3
"""WSGI entry point for production deployment"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import and configure app
from app import create_app
from config import get_config

# Create Flask app with production config
config = get_config()
app = create_app(config)

if __name__ == "__main__":
    # For development: python wsgi.py
    # For production: gunicorn --workers 4 --bind 0.0.0.0:5000 wsgi:app
    app.run(
        host=os.getenv('API_HOST', '0.0.0.0'),
        port=int(os.getenv('API_PORT', 5000)),
        debug=os.getenv('DEBUG', 'False') == 'True'
    )
