#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SIAR Platform - Production Configuration"""

import os
from datetime import timedelta

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    JWT_SECRET = os.getenv('JWT_SECRET', 'dev-jwt-secret-change-in-production')
    JWT_ALGORITHM = 'HS256'
    JWT_EXPIRATION = timedelta(hours=int(os.getenv('JWT_EXPIRATION_HOURS', 24)))
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///./data/orders.db')
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': int(os.getenv('DATABASE_POOL_SIZE', 10)),
        'pool_recycle': int(os.getenv('DATABASE_POOL_RECYCLE', 3600)),
        'pool_pre_ping': True
    }
    RATE_LIMIT_ENABLED = os.getenv('RATE_LIMIT_ENABLED', 'True') == 'True'
    RATE_LIMIT_STORAGE_URL = 'memory://'
    CORS_ENABLED = os.getenv('CORS_ENABLED', 'True') == 'True'
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5000').split(',')
    SECURITY_HEADERS_ENABLED = os.getenv('SECURITY_HEADERS_ENABLED', 'True') == 'True'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))
    MARKETPLACE_API_TIMEOUT = 15
    MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE', 10485760))

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    PREFER_HTTPS = True

class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

def get_config():
    env = os.getenv('FLASK_ENV', 'production')
    if env == 'development':
        return DevelopmentConfig
    elif env == 'testing':
        return TestingConfig
    else:
        return ProductionConfig
