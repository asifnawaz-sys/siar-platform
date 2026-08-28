#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""User Management API Routes - 8 endpoints for complete user lifecycle"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import jwt
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .user_management import UserManagementEngine, User, Role, Permission, AuditLog

user_bp = Blueprint('user_management', __name__, url_prefix='/api/users')

# Database setup
DB_PATH = os.path.join(os.path.dirname(__file__), '../../Data/database/orders.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

def verify_token(request):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return None, jsonify({'error': 'Missing token'}), 401
    try:
        payload = jwt.decode(token, os.getenv('JWT_SECRET', 'dev-secret'), algorithms=['HS256'])
        return payload.get('user_id'), None, None
    except:
        return None, jsonify({'error': 'Invalid token'}), 401

# =====================================================================
# USER MANAGEMENT ENDPOINTS (8)
# =====================================================================

@user_bp.route('', methods=['POST'])
def create_user():
    """Create new user - POST /api/users

    Request:
    {
        "username": "john.doe",
        "email": "john@company.com",
        "password": "secure-password",
        "full_name": "John Doe",
        "roles": ["Sales Manager"]
    }
    """
    session = get_session()
    try:
        data = request.get_json()
        engine = UserManagementEngine(session)

        user = engine.create_user(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password'),
            full_name=data.get('full_name', '')
        )

        if data.get('roles'):
            for role_name in data['roles']:
                engine.assign_role(user.id, role_name)

        session.commit()
        return jsonify({
            'status': 'success',
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'created_at': user.created_at.isoformat()
        }), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        session.close()

@user_bp.route('/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get user details - GET /api/users/<id>"""
    session = get_session()
    try:
        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        roles = [r.name for r in user.roles]
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': user.full_name,
            'is_active': user.is_active,
            'roles': roles,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None
        }), 200
    finally:
        session.close()

@user_bp.route('/<int:user_id>/password', methods=['POST'])
def change_password(user_id):
    """Change user password - POST /api/users/<id>/password

    Request:
    {
        "old_password": "current-password",
        "new_password": "new-secure-password"
    }
    """
    session = get_session()
    try:
        data = request.get_json()
        engine = UserManagementEngine(session)

        result = engine.change_password(
            user_id=user_id,
            old_password=data.get('old_password'),
            new_password=data.get('new_password')
        )

        if result:
            session.commit()
            return jsonify({'status': 'success', 'message': 'Password changed'}), 200
        return jsonify({'error': 'Invalid current password'}), 400
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        session.close()

@user_bp.route('/<int:user_id>/lock', methods=['POST'])
def lock_account(user_id):
    """Lock/unlock user account - POST /api/users/<id>/lock

    Request:
    {"action": "lock"} or {"action": "unlock"}
    """
    session = get_session()
    try:
        data = request.get_json()
        action = data.get('action', 'lock')

        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        user.is_active = (action == 'unlock')
        session.commit()

        return jsonify({
            'status': 'success',
            'user_id': user.id,
            'action': action,
            'is_active': user.is_active
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        session.close()

@user_bp.route('/authenticate', methods=['POST'])
def authenticate():
    """User login - POST /api/users/authenticate

    Request:
    {
        "username": "john.doe",
        "password": "password"
    }
    """
    session = get_session()
    try:
        data = request.get_json()
        engine = UserManagementEngine(session)

        user = session.query(User).filter_by(username=data.get('username')).first()
        if not user or not engine._hash_password(data.get('password')) == user.password_hash:
            return jsonify({'error': 'Invalid credentials'}), 401

        if not user.is_active:
            return jsonify({'error': 'Account is locked'}), 403

        # Update last login
        user.last_login = datetime.utcnow()

        # Generate JWT token
        token = jwt.encode({
            'user_id': user.id,
            'username': user.username,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, os.getenv('JWT_SECRET', 'dev-secret'), algorithm='HS256')

        session.commit()

        return jsonify({
            'status': 'success',
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name
            }
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        session.close()

@user_bp.route('/roles', methods=['POST'])
def create_role():
    """Create new role - POST /api/users/roles

    Request:
    {
        "name": "Warehouse Manager",
        "description": "Manages warehouse operations",
        "permissions": ["view_inventory", "create_grn", "update_stock"]
    }
    """
    session = get_session()
    try:
        data = request.get_json()
        engine = UserManagementEngine(session)

        role = Role(
            name=data.get('name'),
            description=data.get('description', '')
        )
        session.add(role)
        session.flush()

        if data.get('permissions'):
            for perm_name in data['permissions']:
                perm = session.query(Permission).filter_by(name=perm_name).first()
                if perm:
                    role.permissions.append(perm)

        session.commit()
        return jsonify({
            'status': 'success',
            'role_id': role.id,
            'name': role.name,
            'permissions': [p.name for p in role.permissions]
        }), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        session.close()

@user_bp.route('/<int:user_id>/roles', methods=['POST'])
def assign_role(user_id):
    """Assign role to user - POST /api/users/<id>/roles

    Request:
    {"role_name": "Sales Manager"}
    """
    session = get_session()
    try:
        data = request.get_json()
        engine = UserManagementEngine(session)

        user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404

        result = engine.assign_role(user_id, data.get('role_name'))

        if result:
            session.commit()
            roles = [r.name for r in user.roles]
            return jsonify({
                'status': 'success',
                'user_id': user_id,
                'roles': roles
            }), 200
        return jsonify({'error': 'Role not found'}), 404
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 400
    finally:
        session.close()

@user_bp.route('/audit-logs', methods=['GET'])
def get_audit_logs():
    """Get audit trail - GET /api/users/audit-logs?limit=100&offset=0

    Query Parameters:
    - limit: Number of records (default: 100)
    - offset: Starting position (default: 0)
    - user_id: Filter by user (optional)
    - action: Filter by action (optional)
    """
    session = get_session()
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        user_id_filter = request.args.get('user_id', type=int)
        action_filter = request.args.get('action')

        query = session.query(AuditLog)

        if user_id_filter:
            query = query.filter_by(user_id=user_id_filter)
        if action_filter:
            query = query.filter_by(action=action_filter)

        total = query.count()
        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()

        return jsonify({
            'status': 'success',
            'total': total,
            'limit': limit,
            'offset': offset,
            'data': [
                {
                    'id': log.id,
                    'user_id': log.user_id,
                    'action': log.action,
                    'entity_type': log.entity_type,
                    'entity_id': log.entity_id,
                    'changes': log.changes,
                    'timestamp': log.timestamp.isoformat()
                }
                for log in logs
            ]
        }), 200
    finally:
        session.close()
