"""CRM Database Models"""

from sqlalchemy import Column, String, Integer, DateTime, Float, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import json

Base = declarative_base()


class Contact(Base):
    """Customer/Contact Model"""
    __tablename__ = 'crm_contacts'

    id = Column(Integer, primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True)
    phone = Column(String(20))
    company = Column(String(255))
    title = Column(String(100))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    country = Column(String(100))
    notes = Column(Text)
    status = Column(String(50), default='active')  # active, inactive, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leads = relationship("Lead", back_populates="contact", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="contact", cascade="all, delete-orphan")
    communications = relationship("Communication", back_populates="contact", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'email': self.email,
            'phone': self.phone,
            'company': self.company,
            'title': self.title,
            'full_address': f"{self.address or ''}, {self.city or ''}, {self.state or ''} {self.zip_code or ''}".strip(),
            'country': self.country,
            'notes': self.notes,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Lead(Base):
    """Sales Lead Model"""
    __tablename__ = 'crm_leads'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('crm_contacts.id'))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    value = Column(Float, default=0.0)  # Potential deal value
    stage = Column(String(50), default='new')  # new, qualified, proposal, negotiation, closed_won, closed_lost
    probability = Column(Float, default=0.0)  # 0-100%
    expected_close_date = Column(DateTime)
    source = Column(String(100))  # website, referral, social, cold_call, email
    status = Column(String(50), default='active')  # active, inactive, archived
    assigned_to = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contact = relationship("Contact", back_populates="leads")

    def to_dict(self):
        return {
            'id': self.id,
            'contact_id': self.contact_id,
            'title': self.title,
            'description': self.description,
            'value': self.value,
            'stage': self.stage,
            'probability': self.probability,
            'expected_close_date': self.expected_close_date.isoformat() if self.expected_close_date else None,
            'source': self.source,
            'status': self.status,
            'assigned_to': self.assigned_to,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Task(Base):
    """Activity/Task Model"""
    __tablename__ = 'crm_tasks'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('crm_contacts.id'))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    task_type = Column(String(50))  # email, call, meeting, follow_up, reminder
    status = Column(String(50), default='open')  # open, in_progress, completed, cancelled
    priority = Column(String(50), default='medium')  # low, medium, high
    due_date = Column(DateTime)
    assigned_to = Column(String(255))
    completed_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    contact = relationship("Contact", back_populates="tasks")

    def to_dict(self):
        return {
            'id': self.id,
            'contact_id': self.contact_id,
            'title': self.title,
            'description': self.description,
            'task_type': self.task_type,
            'status': self.status,
            'priority': self.priority,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'assigned_to': self.assigned_to,
            'completed_date': self.completed_date.isoformat() if self.completed_date else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Communication(Base):
    """Communication History Model"""
    __tablename__ = 'crm_communications'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('crm_contacts.id'))
    comm_type = Column(String(50))  # email, call, meeting, note, sms
    subject = Column(String(255))
    message = Column(Text)
    direction = Column(String(20))  # inbound, outbound
    status = Column(String(50))  # sent, received, missed, completed
    recipient = Column(String(255))
    duration_minutes = Column(Integer)  # for calls
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    contact = relationship("Contact", back_populates="communications")

    def to_dict(self):
        return {
            'id': self.id,
            'contact_id': self.contact_id,
            'comm_type': self.comm_type,
            'subject': self.subject,
            'message': self.message,
            'direction': self.direction,
            'status': self.status,
            'recipient': self.recipient,
            'duration_minutes': self.duration_minutes,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CrmSetting(Base):
    """CRM Configuration Settings"""
    __tablename__ = 'crm_settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True)
    value = Column(Text)

    def to_dict(self):
        return {
            'key': self.key,
            'value': self.value,
        }
