#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Returns Management System
========================
Complete return orders workflow with refund processing.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class ReturnStatus(enum.Enum):
    """Return order status"""
    REQUESTED = "Requested"
    APPROVED = "Approved"
    IN_TRANSIT = "In Transit"
    RECEIVED = "Received"
    INSPECTION = "Inspection"
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    REFUNDED = "Refunded"


class ItemCondition(enum.Enum):
    """Condition of returned item"""
    SELLABLE = "Sellable"
    DAMAGED = "Damaged"
    DEFECTIVE = "Defective"
    MISSING = "Missing"


class ReturnOrder(Base):
    """Return order master"""
    __tablename__ = 'return_orders'

    id = Column(Integer, primary_key=True)
    return_number = Column(String(50), unique=True, nullable=False, index=True)
    original_order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, index=True)
    original_order_number = Column(String(100))

    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255))

    return_reason = Column(String(255), nullable=False)
    reason_details = Column(Text)

    status = Column(Enum(ReturnStatus), default=ReturnStatus.REQUESTED, index=True)

    requested_date = Column(DateTime, default=datetime.utcnow)
    approval_date = Column(DateTime)
    received_date = Column(DateTime)
    completed_date = Column(DateTime)

    refund_amount = Column(Float, default=0.0)
    refund_status = Column(String(50))  # Pending, Processed, Completed

    return_shipping_label = Column(String(255))
    inbound_tracking_number = Column(String(100))
    warehouse_location = Column(String(100))

    notes = Column(Text)
    approved_by = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship('ReturnItem', back_populates='return_order', cascade='all, delete-orphan')
    history = relationship('ReturnHistory', back_populates='return_order', cascade='all, delete-orphan')


class ReturnItem(Base):
    """Individual item in return order"""
    __tablename__ = 'return_items'

    id = Column(Integer, primary_key=True)
    return_order_id = Column(Integer, ForeignKey('return_orders.id'), nullable=False)
    order_item_id = Column(Integer, ForeignKey('order_items.id'))

    sku_code = Column(String(100), nullable=False)
    product_name = Column(String(255))
    quantity_returned = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)

    condition = Column(Enum(ItemCondition), default=ItemCondition.SELLABLE)
    inspection_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    return_order = relationship('ReturnOrder', back_populates='items')


class ReturnHistory(Base):
    """Return order status history"""
    __tablename__ = 'return_history'

    id = Column(Integer, primary_key=True)
    return_order_id = Column(Integer, ForeignKey('return_orders.id'), nullable=False)
    old_status = Column(String(50))
    new_status = Column(String(50), nullable=False)
    changed_by = Column(String(100))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    return_order = relationship('ReturnOrder', back_populates='history')


class ReturnsEngine:
    """Complete return order management"""

    def __init__(self, db_session, inventory_engine=None):
        self.db = db_session
        self.inventory = inventory_engine

    def create_return_request(self, return_data, user='system'):
        """Create return request"""
        return_order = ReturnOrder(
            return_number=return_data['return_number'],
            original_order_id=return_data['original_order_id'],
            original_order_number=return_data['original_order_number'],
            customer_name=return_data['customer_name'],
            customer_email=return_data.get('customer_email'),
            return_reason=return_data['return_reason'],
            reason_details=return_data.get('reason_details'),
            status=ReturnStatus.REQUESTED,
            notes=return_data.get('notes', '')
        )

        self.db.add(return_order)
        self.db.flush()

        # Add items
        for item_data in return_data.get('items', []):
            item = ReturnItem(
                return_order_id=return_order.id,
                sku_code=item_data['sku_code'],
                product_name=item_data.get('product_name'),
                quantity_returned=item_data['quantity'],
                unit_price=item_data.get('unit_price', 0)
            )
            self.db.add(item)

        self.db.commit()
        self._log_status_change(return_order.id, None, ReturnStatus.REQUESTED.value, user, 'Return requested')

        return {'success': True, 'return_id': return_order.id, 'return_number': return_order.return_number}

    def approve_return(self, return_id, refund_amount, approved_by='system'):
        """Approve return request"""
        return_order = self.db.query(ReturnOrder).filter_by(id=return_id).first()
        if not return_order:
            return {'success': False, 'error': 'Return not found'}

        return_order.status = ReturnStatus.APPROVED
        return_order.approval_date = datetime.utcnow()
        return_order.refund_amount = refund_amount
        return_order.approved_by = approved_by

        self._log_status_change(return_id, ReturnStatus.REQUESTED.value, ReturnStatus.APPROVED.value, approved_by, 'Return approved')
        self.db.commit()

        return {'success': True, 'return_id': return_id, 'refund_amount': refund_amount}

    def receive_return(self, return_id, warehouse_location='', inbound_tracking='', user='system'):
        """Receive returned items"""
        return_order = self.db.query(ReturnOrder).filter_by(id=return_id).first()
        if not return_order:
            return {'success': False, 'error': 'Return not found'}

        return_order.status = ReturnStatus.RECEIVED
        return_order.received_date = datetime.utcnow()
        return_order.warehouse_location = warehouse_location
        return_order.inbound_tracking_number = inbound_tracking

        self._log_status_change(return_id, ReturnStatus.IN_TRANSIT.value, ReturnStatus.RECEIVED.value, user, 'Items received')
        self.db.commit()

        return {'success': True}

    def inspect_return_item(self, return_id, item_id, condition, inspection_notes='', user='system'):
        """Inspect returned item and set condition"""
        item = self.db.query(ReturnItem).filter_by(id=item_id, return_order_id=return_id).first()
        return_order = self.db.query(ReturnOrder).filter_by(id=return_id).first()

        if not item or not return_order:
            return {'success': False, 'error': 'Item or return not found'}

        item.condition = condition
        item.inspection_notes = inspection_notes

        if condition == ItemCondition.SELLABLE:
            if self.inventory:
                self.inventory.add_returned_stock(
                    sku_code=item.sku_code,
                    warehouse_id=return_order.warehouse_location or 1,
                    quantity=item.quantity_returned,
                    reference_number=return_order.return_number,
                    user=user,
                    reason=f'Return {return_order.return_number} - Sellable'
                )
        elif condition == ItemCondition.DAMAGED:
            if self.inventory:
                self.inventory.mark_damaged(
                    sku_code=item.sku_code,
                    warehouse_id=return_order.warehouse_location or 1,
                    quantity=item.quantity_returned,
                    reference_number=return_order.return_number,
                    user=user,
                    reason=f'Return {return_order.return_number} - Damaged'
                )

        self.db.commit()
        return {'success': True}

    def process_refund(self, return_id, user='system'):
        """Process refund for return"""
        return_order = self.db.query(ReturnOrder).filter_by(id=return_id).first()
        if not return_order:
            return {'success': False, 'error': 'Return not found'}

        return_order.status = ReturnStatus.REFUNDED
        return_order.refund_status = 'Processed'
        return_order.completed_date = datetime.utcnow()

        self._log_status_change(return_id, ReturnStatus.INSPECTION.value, ReturnStatus.REFUNDED.value, user, 'Refund processed')
        self.db.commit()

        return {'success': True, 'refund_amount': return_order.refund_amount}

    def reject_return(self, return_id, rejection_reason='', user='system'):
        """Reject return request"""
        return_order = self.db.query(ReturnOrder).filter_by(id=return_id).first()
        if not return_order:
            return {'success': False, 'error': 'Return not found'}

        return_order.status = ReturnStatus.REJECTED
        return_order.notes = rejection_reason

        self._log_status_change(return_id, None, ReturnStatus.REJECTED.value, user, rejection_reason)
        self.db.commit()

        return {'success': True}

    def get_return_order(self, return_id):
        """Get return order details"""
        return_order = self.db.query(ReturnOrder).filter_by(id=return_id).first()
        if not return_order:
            return None

        return {
            'id': return_order.id,
            'return_number': return_order.return_number,
            'original_order_number': return_order.original_order_number,
            'customer_name': return_order.customer_name,
            'status': return_order.status.value if return_order.status else None,
            'refund_amount': return_order.refund_amount,
            'requested_date': return_order.requested_date.isoformat() if return_order.requested_date else None,
            'items': [
                {
                    'sku': item.sku_code,
                    'quantity': item.quantity_returned,
                    'condition': item.condition.value if item.condition else None
                }
                for item in return_order.items
            ]
        }

    def _log_status_change(self, return_id, old_status, new_status, user, reason):
        """Log status change"""
        history = ReturnHistory(
            return_order_id=return_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            change_reason=reason
        )
        self.db.add(history)
        self.db.commit()
