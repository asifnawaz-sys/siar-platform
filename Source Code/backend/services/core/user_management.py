#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
User Management & Role-Based Access Control
=============================================
Complete RBAC system with users, roles, permissions, and audit trail.
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Enum, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import os

Base = declarative_base()


class UserRole(enum.Enum):
    """User roles in the system"""
    SUPER_ADMIN = "Super Admin"
    ADMIN = "Admin"
    MANAGER = "Manager"
    WAREHOUSE_LEAD = "Warehouse Lead"
    WAREHOUSE_STAFF = "Warehouse Staff"
    PACKER = "Packer"
    PICKER = "Picker"
    CUSTOMER_SUPPORT = "Customer Support"
    FINANCE = "Finance"
    VIEWER = "Viewer"


class PermissionType(enum.Enum):
    """System permissions"""
    # Order Management
    VIEW_ORDERS = "view_orders"
    CREATE_ORDERS = "create_orders"
    EDIT_ORDERS = "edit_orders"
    CANCEL_ORDERS = "cancel_orders"

    # Inventory Management
    VIEW_INVENTORY = "view_inventory"
    EDIT_INVENTORY = "edit_inventory"
    ADJUST_INVENTORY = "adjust_inventory"

    # Fulfillment
    VIEW_FULFILLMENT = "view_fulfillment"
    MANAGE_PICKING = "manage_picking"
    MANAGE_PACKING = "manage_packing"
    MANAGE_SHIPMENTS = "manage_shipments"

    # Returns
    VIEW_RETURNS = "view_returns"
    PROCESS_RETURNS = "process_returns"

    # Marketplace
    VIEW_INTEGRATIONS = "view_integrations"
    MANAGE_INTEGRATIONS = "manage_integrations"

    # Users & Roles
    VIEW_USERS = "view_users"
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"

    # Reporting
    VIEW_REPORTS = "view_reports"
    EXPORT_REPORTS = "export_reports"

    # Settings
    VIEW_SETTINGS = "view_settings"
    MANAGE_SETTINGS = "manage_settings"


# Association table for User-Role many-to-many relationship
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True)
)

# Association table for Role-Permission many-to-many relationship
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id'), primary_key=True)
)


class User(Base):
    """System user"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    password_hash = Column(String(500), nullable=False)

    is_active = Column(Boolean, default=True, index=True)
    is_locked = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)

    last_login = Column(DateTime)
    last_login_ip = Column(String(50))
    last_password_change = Column(DateTime)

    phone = Column(String(20))
    department = Column(String(100))
    manager_id = Column(Integer, ForeignKey('users.id'))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(100))

    roles = relationship('Role', secondary=user_roles, back_populates='users', cascade='all')
    audit_logs = relationship('AuditLog', back_populates='user', cascade='all, delete-orphan')
    activity_logs = relationship('UserActivityLog', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        self.last_password_change = datetime.utcnow()

    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)

    def get_all_permissions(self):
        """Get all permissions from assigned roles"""
        permissions = set()
        for role in self.roles:
            permissions.update([p.permission_type for p in role.permissions])
        return permissions

    def has_permission(self, permission):
        """Check if user has specific permission"""
        return permission in self.get_all_permissions()

    def has_role(self, role_name):
        """Check if user has specific role"""
        return any(r.role_name == role_name for r in self.roles)


class Role(Base):
    """User role"""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    role_name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)

    is_system_role = Column(Boolean, default=False)  # Cannot be deleted if True
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))

    users = relationship('User', secondary=user_roles, back_populates='roles', cascade='all')
    permissions = relationship('Permission', secondary=role_permissions, back_populates='roles', cascade='all')


class Permission(Base):
    """System permission"""
    __tablename__ = 'permissions'

    id = Column(Integer, primary_key=True)
    permission_type = Column(Enum(PermissionType), unique=True, nullable=False, index=True)
    description = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    roles = relationship('Role', secondary=role_permissions, back_populates='permissions', cascade='all')


class AuditLog(Base):
    """System audit trail"""
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    action = Column(String(255), nullable=False)
    entity_type = Column(String(100), nullable=False)  # Order, Inventory, User, etc.
    entity_id = Column(Integer)
    old_value = Column(Text)
    new_value = Column(Text)
    ip_address = Column(String(50))
    user_agent = Column(String(500))

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship('User', back_populates='audit_logs')


class UserActivityLog(Base):
    """User activity tracking"""
    __tablename__ = 'user_activity_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    activity_type = Column(String(100), nullable=False)  # LOGIN, LOGOUT, VIEW, CREATE, UPDATE, DELETE
    resource = Column(String(255))  # What was accessed/modified
    status = Column(String(50))  # SUCCESS, FAILURE, WARNING
    details = Column(Text)
    ip_address = Column(String(50))

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship('User', back_populates='activity_logs')


class UserManagementEngine:
    """Complete user and role management"""

    def __init__(self, db_session, jwt_secret=None):
        self.db = db_session
        self.jwt_secret = jwt_secret or os.getenv('JWT_SECRET', 'dev-secret-key')

    # =====================================================================
    # USER MANAGEMENT
    # =====================================================================

    def create_user(self, username, email, password, full_name, department='', created_by='system'):
        """Create new user"""
        # Check if user exists
        existing = self.db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing:
            return {'success': False, 'error': 'User already exists'}

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            department=department,
            created_by=created_by
        )
        user.set_password(password)

        self.db.add(user)
        self.db.commit()

        self._log_audit(created_by, 'CREATE', 'User', user.id, None, f'User {username} created')

        return {'success': True, 'user_id': user.id, 'username': username}

    def update_user(self, user_id, full_name=None, phone=None, department=None, manager_id=None, user='system'):
        """Update user details"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return {'success': False, 'error': 'User not found'}

        changes = []
        if full_name and full_name != u.full_name:
            changes.append(f'name: {u.full_name} → {full_name}')
            u.full_name = full_name
        if phone and phone != u.phone:
            changes.append(f'phone: {u.phone} → {phone}')
            u.phone = phone
        if department and department != u.department:
            changes.append(f'department: {u.department} → {department}')
            u.department = department
        if manager_id is not None and manager_id != u.manager_id:
            changes.append(f'manager_id: {u.manager_id} → {manager_id}')
            u.manager_id = manager_id

        if changes:
            self.db.commit()
            self._log_audit(user, 'UPDATE', 'User', user_id, None, ', '.join(changes))

        return {'success': True}

    def change_password(self, user_id, old_password, new_password, user='system'):
        """Change user password"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return {'success': False, 'error': 'User not found'}

        if not u.check_password(old_password):
            self._log_activity(user_id, 'CHANGE_PASSWORD', 'Password', 'FAILURE', 'Invalid old password')
            return {'success': False, 'error': 'Invalid current password'}

        u.set_password(new_password)
        self.db.commit()

        self._log_activity(user_id, 'CHANGE_PASSWORD', 'Password', 'SUCCESS', 'Password changed')
        self._log_audit(user, 'UPDATE', 'User', user_id, 'password', 'Password changed')

        return {'success': True}

    def reset_password(self, user_id, new_password, user='system'):
        """Reset user password (admin action)"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return {'success': False, 'error': 'User not found'}

        u.set_password(new_password)
        u.failed_login_attempts = 0
        self.db.commit()

        self._log_audit(user, 'UPDATE', 'User', user_id, 'password', f'Password reset by {user}')
        self._log_activity(user_id, 'PASSWORD_RESET', 'Password', 'SUCCESS', f'Password reset by {user}')

        return {'success': True}

    def lock_user(self, user_id, user='system'):
        """Lock user account"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return {'success': False, 'error': 'User not found'}

        u.is_locked = True
        self.db.commit()

        self._log_audit(user, 'UPDATE', 'User', user_id, 'is_locked', f'Account locked by {user}')

        return {'success': True}

    def unlock_user(self, user_id, user='system'):
        """Unlock user account"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return {'success': False, 'error': 'User not found'}

        u.is_locked = False
        u.failed_login_attempts = 0
        self.db.commit()

        self._log_audit(user, 'UPDATE', 'User', user_id, 'is_locked', f'Account unlocked by {user}')

        return {'success': True}

    def deactivate_user(self, user_id, user='system'):
        """Deactivate user"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return {'success': False, 'error': 'User not found'}

        u.is_active = False
        self.db.commit()

        self._log_audit(user, 'UPDATE', 'User', user_id, 'is_active', f'User deactivated by {user}')

        return {'success': True}

    def authenticate(self, username, password, ip_address=''):
        """Authenticate user and return JWT token"""
        u = self.db.query(User).filter_by(username=username).first()

        if not u or not u.check_password(password):
            self._log_activity(None, 'LOGIN', username, 'FAILURE', 'Invalid credentials', ip_address)
            return {'success': False, 'error': 'Invalid username or password'}

        if u.is_locked:
            self._log_activity(u.id, 'LOGIN', username, 'FAILURE', 'Account locked', ip_address)
            return {'success': False, 'error': 'Account is locked'}

        if not u.is_active:
            self._log_activity(u.id, 'LOGIN', username, 'FAILURE', 'Account inactive', ip_address)
            return {'success': False, 'error': 'Account is inactive'}

        # Reset failed login attempts
        u.failed_login_attempts = 0
        u.last_login = datetime.utcnow()
        u.last_login_ip = ip_address
        self.db.commit()

        # Generate JWT token
        payload = {
            'user_id': u.id,
            'username': u.username,
            'roles': [r.role_name for r in u.roles],
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')

        self._log_activity(u.id, 'LOGIN', username, 'SUCCESS', 'Login successful', ip_address)

        return {
            'success': True,
            'token': token,
            'user_id': u.id,
            'username': u.username,
            'full_name': u.full_name
        }

    def get_user(self, user_id):
        """Get user details"""
        u = self.db.query(User).filter_by(id=user_id).first()
        if not u:
            return None

        return {
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'full_name': u.full_name,
            'department': u.department,
            'phone': u.phone,
            'is_active': u.is_active,
            'is_locked': u.is_locked,
            'roles': [r.role_name for r in u.roles],
            'permissions': list(u.get_all_permissions()),
            'last_login': u.last_login.isoformat() if u.last_login else None,
            'created_at': u.created_at.isoformat() if u.created_at else None
        }

    # =====================================================================
    # ROLE MANAGEMENT
    # =====================================================================

    def create_role(self, role_name, description='', permissions=None, created_by='system'):
        """Create new role"""
        role = Role(
            role_name=role_name,
            description=description,
            created_by=created_by
        )

        if permissions:
            for perm_type in permissions:
                perm = self.db.query(Permission).filter_by(permission_type=perm_type).first()
                if perm:
                    role.permissions.append(perm)

        self.db.add(role)
        self.db.commit()

        return {'success': True, 'role_id': role.id}

    def assign_role(self, user_id, role_id, user='system'):
        """Assign role to user"""
        u = self.db.query(User).filter_by(id=user_id).first()
        role = self.db.query(Role).filter_by(id=role_id).first()

        if not u or not role:
            return {'success': False, 'error': 'User or role not found'}

        if role not in u.roles:
            u.roles.append(role)
            self.db.commit()
            self._log_audit(user, 'UPDATE', 'User', user_id, None, f'Role {role.role_name} assigned')

        return {'success': True}

    def remove_role(self, user_id, role_id, user='system'):
        """Remove role from user"""
        u = self.db.query(User).filter_by(id=user_id).first()
        role = self.db.query(Role).filter_by(id=role_id).first()

        if not u or not role:
            return {'success': False, 'error': 'User or role not found'}

        if role in u.roles:
            u.roles.remove(role)
            self.db.commit()
            self._log_audit(user, 'UPDATE', 'User', user_id, None, f'Role {role.role_name} removed')

        return {'success': True}

    def get_role_permissions(self, role_id):
        """Get permissions for role"""
        role = self.db.query(Role).filter_by(id=role_id).first()
        if not role:
            return None

        return {
            'role_id': role.id,
            'role_name': role.role_name,
            'permissions': [p.permission_type.value for p in role.permissions]
        }

    # =====================================================================
    # AUDIT & ACTIVITY LOGGING
    # =====================================================================

    def get_audit_logs(self, entity_type=None, entity_id=None, days=30, limit=1000):
        """Get audit logs"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        query = self.db.query(AuditLog).filter(AuditLog.created_at >= cutoff_date)

        if entity_type:
            query = query.filter_by(entity_type=entity_type)
        if entity_id:
            query = query.filter_by(entity_id=entity_id)

        logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

        return [
            {
                'timestamp': log.created_at.isoformat(),
                'user': log.user.username if log.user else 'system',
                'action': log.action,
                'entity_type': log.entity_type,
                'entity_id': log.entity_id,
                'old_value': log.old_value,
                'new_value': log.new_value
            }
            for log in logs
        ]

    def get_user_activity(self, user_id, days=7, limit=500):
        """Get user activity log"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        logs = self.db.query(UserActivityLog).filter(
            UserActivityLog.user_id == user_id,
            UserActivityLog.created_at >= cutoff_date
        ).order_by(UserActivityLog.created_at.desc()).limit(limit).all()

        return [
            {
                'timestamp': log.created_at.isoformat(),
                'activity': log.activity_type,
                'resource': log.resource,
                'status': log.status,
                'details': log.details
            }
            for log in logs
        ]

    # =====================================================================
    # INTERNAL HELPERS
    # =====================================================================

    def _log_audit(self, user, action, entity_type, entity_id, old_value, new_value):
        """Log audit trail"""
        audit = AuditLog(
            user_id=self.db.query(User).filter_by(username=user).first().id if isinstance(user, str) else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value
        )
        self.db.add(audit)
        self.db.commit()

    def _log_activity(self, user_id, activity_type, resource, status, details, ip_address=''):
        """Log user activity"""
        if user_id:
            activity = UserActivityLog(
                user_id=user_id,
                activity_type=activity_type,
                resource=resource,
                status=status,
                details=details,
                ip_address=ip_address
            )
            self.db.add(activity)
            self.db.commit()
