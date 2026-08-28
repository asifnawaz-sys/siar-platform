#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Customer Relationship Management (CRM)
======================================
Complete CRM system with customer profiles, interactions, and analytics.
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class CustomerSegment(enum.Enum):
    """Customer segmentation"""
    PLATINUM = "Platinum"
    GOLD = "Gold"
    SILVER = "Silver"
    BRONZE = "Bronze"
    NEW = "New"


class InteractionType(enum.Enum):
    """Customer interaction types"""
    PHONE = "Phone Call"
    EMAIL = "Email"
    CHAT = "Chat"
    VISIT = "Visit"
    ORDER = "Order"
    RETURN = "Return"
    COMPLAINT = "Complaint"
    FEEDBACK = "Feedback"
    NOTE = "Internal Note"


class CustomerProfile(Base):
    """Customer profile master"""
    __tablename__ = 'customer_profiles'

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=False, unique=True)

    segment = Column(Enum(CustomerSegment), default=CustomerSegment.NEW, index=True)
    loyalty_points = Column(Integer, default=0)
    lifetime_value = Column(Float, default=0.0)
    total_orders = Column(Integer, default=0)
    total_spent = Column(Float, default=0.0)

    average_order_value = Column(Float, default=0.0)
    last_order_date = Column(DateTime)
    days_since_last_order = Column(Integer)

    preferred_payment_method = Column(String(50))
    preferred_delivery_option = Column(String(100))
    notes = Column(Text)

    is_vip = Column(Boolean, default=False)
    is_blacklisted = Column(Boolean, default=False)
    blacklist_reason = Column(String(255))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship('Customer', back_populates='profile')
    interactions = relationship('CustomerInteraction', back_populates='profile', cascade='all, delete-orphan')
    preferences = relationship('CustomerPreference', back_populates='profile', cascade='all, delete-orphan')


class CustomerInteraction(Base):
    """Customer interaction/touchpoint"""
    __tablename__ = 'customer_interactions'

    id = Column(Integer, primary_key=True)
    customer_profile_id = Column(Integer, ForeignKey('customer_profiles.id'), nullable=False)
    interaction_type = Column(Enum(InteractionType), nullable=False, index=True)

    subject = Column(String(255))
    description = Column(Text)
    resolution = Column(Text)

    handled_by = Column(String(100))
    satisfaction_rating = Column(Integer)  # 1-5

    interaction_date = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_date = Column(DateTime)

    related_order_id = Column(Integer)
    related_return_id = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship('CustomerProfile', back_populates='interactions')


class CustomerPreference(Base):
    """Customer preferences"""
    __tablename__ = 'customer_preferences'

    id = Column(Integer, primary_key=True)
    customer_profile_id = Column(Integer, ForeignKey('customer_profiles.id'), nullable=False)

    preferred_language = Column(String(50), default='en')
    communication_preference = Column(String(50))  # Email, SMS, Phone, etc.
    opt_in_marketing = Column(Boolean, default=True)
    opt_in_notifications = Column(Boolean, default=True)

    birthday = Column(String(10))  # MM-DD format
    anniversary = Column(String(10))

    size_preference = Column(String(50))
    color_preference = Column(String(100))
    brand_preferences = Column(JSON)  # List of preferred brands

    dietary_restrictions = Column(JSON)
    accessibility_needs = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship('CustomerProfile', back_populates='preferences')


class CRMEngine:
    """Complete customer relationship management"""

    def __init__(self, db_session):
        self.db = db_session

    # =====================================================================
    # CUSTOMER PROFILE MANAGEMENT
    # =====================================================================

    def create_customer_profile(self, customer_id):
        """Create customer profile"""
        profile = CustomerProfile(customer_id=customer_id)
        self.db.add(profile)
        self.db.commit()

        return {'success': True, 'profile_id': profile.id}

    def update_customer_segment(self, customer_id):
        """Update customer segment based on behavior"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return {'success': False, 'error': 'Profile not found'}

        # Segmentation logic
        lifetime_value = profile.lifetime_value
        total_orders = profile.total_orders

        if lifetime_value > 100000 or total_orders > 50:
            new_segment = CustomerSegment.PLATINUM
        elif lifetime_value > 50000 or total_orders > 25:
            new_segment = CustomerSegment.GOLD
        elif lifetime_value > 20000 or total_orders > 10:
            new_segment = CustomerSegment.SILVER
        elif lifetime_value > 5000 or total_orders > 3:
            new_segment = CustomerSegment.BRONZE
        else:
            new_segment = CustomerSegment.NEW

        old_segment = profile.segment
        profile.segment = new_segment

        # Update VIP status
        profile.is_vip = (new_segment in [CustomerSegment.PLATINUM, CustomerSegment.GOLD])

        self.db.commit()

        return {
            'success': True,
            'old_segment': old_segment.value if old_segment else None,
            'new_segment': new_segment.value,
            'is_vip': profile.is_vip
        }

    def update_customer_metrics(self, customer_id, order_amount, user='system'):
        """Update customer profile metrics after order"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return {'success': False, 'error': 'Profile not found'}

        profile.total_orders += 1
        profile.total_spent += order_amount
        profile.average_order_value = profile.total_spent / profile.total_orders
        profile.last_order_date = datetime.utcnow()
        profile.days_since_last_order = 0

        # Award loyalty points (1 point per rupee)
        points_earned = int(order_amount)
        profile.loyalty_points += points_earned

        # Update lifetime value
        profile.lifetime_value = profile.total_spent

        self.db.commit()

        # Update segment
        self.update_customer_segment(customer_id)

        return {
            'success': True,
            'points_earned': points_earned,
            'total_points': profile.loyalty_points,
            'total_spent': profile.total_spent
        }

    def add_vip_status(self, customer_id, user='system'):
        """Mark customer as VIP"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return {'success': False, 'error': 'Profile not found'}

        profile.is_vip = True
        self.db.commit()

        return {'success': True}

    def blacklist_customer(self, customer_id, reason, user='system'):
        """Blacklist customer"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return {'success': False, 'error': 'Profile not found'}

        profile.is_blacklisted = True
        profile.blacklist_reason = reason

        self.db.commit()

        return {'success': True, 'reason': reason}

    # =====================================================================
    # CUSTOMER INTERACTIONS
    # =====================================================================

    def record_interaction(self, customer_id, interaction_type, subject, description,
                          handled_by='system', related_order_id=None, related_return_id=None):
        """Record customer interaction"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return {'success': False, 'error': 'Profile not found'}

        interaction = CustomerInteraction(
            customer_profile_id=profile.id,
            interaction_type=interaction_type,
            subject=subject,
            description=description,
            handled_by=handled_by,
            related_order_id=related_order_id,
            related_return_id=related_return_id
        )

        self.db.add(interaction)
        self.db.commit()

        return {'success': True, 'interaction_id': interaction.id}

    def resolve_interaction(self, interaction_id, resolution, satisfaction_rating=None, user='system'):
        """Resolve customer interaction"""
        interaction = self.db.query(CustomerInteraction).filter_by(id=interaction_id).first()
        if not interaction:
            return {'success': False, 'error': 'Interaction not found'}

        interaction.resolution = resolution
        interaction.resolved_date = datetime.utcnow()
        if satisfaction_rating:
            interaction.satisfaction_rating = satisfaction_rating

        self.db.commit()

        return {'success': True}

    def get_customer_interactions(self, customer_id, limit=50):
        """Get customer interaction history"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return []

        interactions = self.db.query(CustomerInteraction).filter_by(
            customer_profile_id=profile.id
        ).order_by(CustomerInteraction.interaction_date.desc()).limit(limit).all()

        return [
            {
                'id': i.id,
                'type': i.interaction_type.value if i.interaction_type else None,
                'subject': i.subject,
                'description': i.description,
                'handled_by': i.handled_by,
                'satisfaction_rating': i.satisfaction_rating,
                'interaction_date': i.interaction_date.isoformat() if i.interaction_date else None,
                'resolved_date': i.resolved_date.isoformat() if i.resolved_date else None,
                'status': 'Resolved' if i.resolved_date else 'Open'
            }
            for i in interactions
        ]

    # =====================================================================
    # CUSTOMER PREFERENCES
    # =====================================================================

    def save_preferences(self, customer_id, preferences_data):
        """Save customer preferences"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return {'success': False, 'error': 'Profile not found'}

        pref = self.db.query(CustomerPreference).filter_by(customer_profile_id=profile.id).first()
        if not pref:
            pref = CustomerPreference(customer_profile_id=profile.id)
            self.db.add(pref)

        # Update preference fields
        for key, value in preferences_data.items():
            if hasattr(pref, key):
                setattr(pref, key, value)

        self.db.commit()

        return {'success': True}

    def get_preferences(self, customer_id):
        """Get customer preferences"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return None

        pref = self.db.query(CustomerPreference).filter_by(customer_profile_id=profile.id).first()
        if not pref:
            return None

        return {
            'language': pref.preferred_language,
            'communication': pref.communication_preference,
            'marketing_opt_in': pref.opt_in_marketing,
            'notifications_opt_in': pref.opt_in_notifications,
            'birthday': pref.birthday,
            'anniversary': pref.anniversary,
            'size_preference': pref.size_preference,
            'color_preference': pref.color_preference,
            'brands': pref.brand_preferences,
            'dietary_restrictions': pref.dietary_restrictions,
            'accessibility_needs': pref.accessibility_needs
        }

    # =====================================================================
    # CRM ANALYTICS
    # =====================================================================

    def get_customer_profile_summary(self, customer_id):
        """Get complete customer profile summary"""
        profile = self.db.query(CustomerProfile).filter_by(customer_id=customer_id).first()
        if not profile:
            return None

        return {
            'segment': profile.segment.value if profile.segment else None,
            'loyalty_points': profile.loyalty_points,
            'lifetime_value': round(profile.lifetime_value, 2),
            'total_orders': profile.total_orders,
            'total_spent': round(profile.total_spent, 2),
            'average_order_value': round(profile.average_order_value, 2),
            'last_order_date': profile.last_order_date.isoformat() if profile.last_order_date else None,
            'is_vip': profile.is_vip,
            'is_blacklisted': profile.is_blacklisted,
            'recent_interactions': self.get_customer_interactions(customer_id, limit=5),
            'preferences': self.get_preferences(customer_id)
        }

    def get_churn_risk_customers(self, days_inactive=90, limit=100):
        """Get customers at risk of churning"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_inactive)

        at_risk = self.db.query(CustomerProfile).filter(
            CustomerProfile.last_order_date < cutoff_date,
            CustomerProfile.total_orders > 0,
            CustomerProfile.is_blacklisted == False
        ).order_by(CustomerProfile.last_order_date.asc()).limit(limit).all()

        return [
            {
                'customer_id': p.customer_id,
                'segment': p.segment.value if p.segment else None,
                'lifetime_value': p.lifetime_value,
                'last_order_date': p.last_order_date.isoformat() if p.last_order_date else None,
                'days_inactive': (datetime.utcnow() - p.last_order_date).days if p.last_order_date else None
            }
            for p in at_risk
        ]

    def get_high_value_customers(self, min_lifetime_value=50000, limit=100):
        """Get high-value customers"""
        customers = self.db.query(CustomerProfile).filter(
            CustomerProfile.lifetime_value >= min_lifetime_value,
            CustomerProfile.is_blacklisted == False
        ).order_by(CustomerProfile.lifetime_value.desc()).limit(limit).all()

        return [
            {
                'customer_id': p.customer_id,
                'lifetime_value': p.lifetime_value,
                'total_orders': p.total_orders,
                'average_order_value': p.average_order_value,
                'segment': p.segment.value if p.segment else None
            }
            for p in customers
        ]

    def get_segment_statistics(self):
        """Get statistics by customer segment"""
        segments = {}

        for segment in CustomerSegment:
            customers = self.db.query(CustomerProfile).filter_by(segment=segment).all()
            count = len(customers)
            total_value = sum(c.lifetime_value for c in customers)
            avg_value = total_value / count if count > 0 else 0
            total_orders = sum(c.total_orders for c in customers)

            segments[segment.value] = {
                'customer_count': count,
                'total_lifetime_value': round(total_value, 2),
                'average_customer_value': round(avg_value, 2),
                'total_orders': total_orders,
                'average_orders_per_customer': round(total_orders / count, 2) if count > 0 else 0
            }

        return segments
