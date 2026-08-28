#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GRN (Goods Receipt Note) Engine
===============================
Complete inbound goods receiving and inventory posting system.
Follows ERP principles with full audit trail and approval workflow.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

# =====================================================================
# GRN STATUS ENUM
# =====================================================================

class GRNStatus(enum.Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    INSPECTION = "Inspection"
    APPROVED = "Approved"
    POSTED = "Posted"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"


class GRNModel(Base):
    """GRN (Goods Receipt Note) Master"""
    __tablename__ = 'grns'

    id = Column(Integer, primary_key=True)
    grn_number = Column(String(50), unique=True, nullable=False, index=True)
    po_reference = Column(String(100))

    supplier_name = Column(String(255), nullable=False)
    supplier_email = Column(String(255))
    supplier_phone = Column(String(50))

    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    brand = Column(String(100))

    grn_date = Column(DateTime, default=datetime.utcnow)
    expected_delivery_date = Column(DateTime)
    actual_delivery_date = Column(DateTime)

    status = Column(Enum(GRNStatus), default=GRNStatus.DRAFT, index=True)

    total_expected_cost = Column(Float, default=0.0)
    total_received_cost = Column(Float, default=0.0)
    total_accepted_cost = Column(Float, default=0.0)

    notes = Column(Text)
    rejection_reason = Column(Text)

    created_by = Column(String(100))
    submitted_by = Column(String(100))
    approved_by = Column(String(100))
    submitted_date = Column(DateTime)
    approved_date = Column(DateTime)
    posted_date = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = relationship('GRNItem', back_populates='grn', cascade='all, delete-orphan')
    history = relationship('GRNHistory', back_populates='grn', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'grn_number': self.grn_number,
            'po_reference': self.po_reference,
            'supplier': self.supplier_name,
            'warehouse_id': self.warehouse_id,
            'status': self.status.value if self.status else None,
            'total_expected_cost': self.total_expected_cost,
            'total_accepted_cost': self.total_accepted_cost,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'item_count': len(self.items),
            'items': [item.to_dict() for item in self.items]
        }


class GRNItem(Base):
    """GRN Line Item"""
    __tablename__ = 'grn_items'

    id = Column(Integer, primary_key=True)
    grn_id = Column(Integer, ForeignKey('grns.id'), nullable=False, index=True)
    sku_id = Column(Integer, ForeignKey('sku_master.id'), nullable=False, index=True)

    sku_code = Column(String(100), nullable=False)
    product_name = Column(String(255))
    variant = Column(String(100))
    size = Column(String(50))
    color = Column(String(50))

    expected_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer, default=0)
    accepted_quantity = Column(Integer, default=0)
    rejected_quantity = Column(Integer, default=0)
    damaged_quantity = Column(Integer, default=0)

    unit_cost = Column(Float, nullable=False)
    total_expected_cost = Column(Float, nullable=False)

    batch_number = Column(String(100))
    expiry_date = Column(DateTime)
    manufacturing_date = Column(DateTime)

    remarks = Column(Text)
    inspection_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    grn = relationship('GRNModel', back_populates='items')

    def to_dict(self):
        return {
            'id': self.id,
            'sku_code': self.sku_code,
            'product_name': self.product_name,
            'expected_quantity': self.expected_quantity,
            'received_quantity': self.received_quantity,
            'accepted_quantity': self.accepted_quantity,
            'damaged_quantity': self.damaged_quantity,
            'unit_cost': self.unit_cost,
            'total_cost': self.expected_quantity * self.unit_cost
        }


class GRNHistory(Base):
    """GRN Status Change History"""
    __tablename__ = 'grn_history'

    id = Column(Integer, primary_key=True)
    grn_id = Column(Integer, ForeignKey('grns.id'), nullable=False, index=True)

    old_status = Column(String(50))
    new_status = Column(String(50), nullable=False)
    changed_by = Column(String(100))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    grn = relationship('GRNModel', back_populates='history')


# =====================================================================
# GRN ENGINE
# =====================================================================

class GRNEngine:
    """Complete GRN workflow management"""

    def __init__(self, db_session, inventory_engine=None):
        self.db = db_session
        self.inventory = inventory_engine

    # =====================================================================
    # GRN CREATION
    # =====================================================================

    def create_grn(self, grn_data, user='system'):
        """Create new GRN (Draft status)"""
        grn = GRNModel(
            grn_number=grn_data['grn_number'],
            po_reference=grn_data.get('po_reference'),
            supplier_name=grn_data['supplier_name'],
            supplier_email=grn_data.get('supplier_email'),
            supplier_phone=grn_data.get('supplier_phone'),
            warehouse_id=grn_data['warehouse_id'],
            brand=grn_data.get('brand'),
            notes=grn_data.get('notes', ''),
            created_by=user,
            status=GRNStatus.DRAFT
        )

        self.db.add(grn)
        self.db.flush()

        # Add items
        total_expected = 0
        for item_data in grn_data.get('items', []):
            item = GRNItem(
                grn_id=grn.id,
                sku_code=item_data['sku_code'],
                product_name=item_data.get('product_name'),
                expected_quantity=item_data['expected_quantity'],
                unit_cost=item_data.get('unit_cost', 0),
                batch_number=item_data.get('batch_number')
            )
            item.total_expected_cost = item.expected_quantity * item.unit_cost
            total_expected += item.total_expected_cost
            self.db.add(item)

        grn.total_expected_cost = total_expected
        self.db.commit()

        self._log_status_change(grn.id, None, GRNStatus.DRAFT.value, user, 'GRN created')

        return {'success': True, 'grn_id': grn.id, 'grn_number': grn.grn_number}

    # =====================================================================
    # GRN STATUS TRANSITIONS
    # =====================================================================

    def submit_grn(self, grn_id, user='system'):
        """Submit GRN for inspection"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        if not grn or grn.status != GRNStatus.DRAFT:
            return {'success': False, 'error': 'Invalid GRN status for submission'}

        grn.status = GRNStatus.SUBMITTED
        grn.submitted_by = user
        grn.submitted_date = datetime.utcnow()

        self._log_status_change(grn_id, GRNStatus.DRAFT.value, GRNStatus.SUBMITTED.value, user, 'GRN submitted')
        self.db.commit()

        return {'success': True, 'grn_id': grn_id}

    def move_to_inspection(self, grn_id, user='system'):
        """Move to inspection"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        if not grn:
            return {'success': False, 'error': 'GRN not found'}

        old_status = grn.status.value if grn.status else None
        grn.status = GRNStatus.INSPECTION

        self._log_status_change(grn_id, old_status, GRNStatus.INSPECTION.value, user, 'Moved to inspection')
        self.db.commit()

        return {'success': True}

    def receive_grn_item(self, grn_id, grn_item_id, received_qty, damaged_qty=0, user='system'):
        """Record received quantity for GRN item"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        item = self.db.query(GRNItem).filter_by(id=grn_item_id, grn_id=grn_id).first()

        if not grn or not item:
            return {'success': False, 'error': 'GRN or item not found'}

        item.received_quantity = received_qty
        item.damaged_quantity = damaged_qty
        item.accepted_quantity = received_qty - damaged_qty

        self.db.commit()
        return {'success': True, 'received': received_qty, 'accepted': item.accepted_quantity}

    def approve_grn(self, grn_id, user='system'):
        """Approve GRN - ready to post to inventory"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        if not grn or grn.status not in [GRNStatus.INSPECTION, GRNStatus.SUBMITTED]:
            return {'success': False, 'error': 'Invalid GRN status for approval'}

        grn.status = GRNStatus.APPROVED
        grn.approved_by = user
        grn.approved_date = datetime.utcnow()

        # Recalculate costs
        total_accepted = sum(item.accepted_quantity * item.unit_cost for item in grn.items)
        grn.total_accepted_cost = total_accepted

        self._log_status_change(grn_id, GRNStatus.INSPECTION.value, GRNStatus.APPROVED.value, user, 'GRN approved')
        self.db.commit()

        return {'success': True, 'grn_id': grn_id, 'total_cost': total_accepted}

    def post_grn_to_inventory(self, grn_id, user='system'):
        """Post approved GRN to inventory - updates stock"""
        if not self.inventory:
            return {'success': False, 'error': 'Inventory engine not available'}

        grn = self.db.query(GRNModel).filter_by(id=grn_id, status=GRNStatus.APPROVED).first()
        if not grn:
            return {'success': False, 'error': 'GRN not approved'}

        # Add to inventory
        for item in grn.items:
            if item.accepted_quantity > 0:
                result = self.inventory.add_stock(
                    sku_code=item.sku_code,
                    warehouse_id=grn.warehouse_id,
                    quantity=item.accepted_quantity,
                    movement_type='GRN',
                    reference_number=grn.grn_number,
                    user=user,
                    reason=f'GRN {grn.grn_number} posted'
                )

                if not result['success']:
                    return result

            # Mark damaged if applicable
            if item.damaged_quantity > 0:
                self.inventory.mark_damaged(
                    sku_code=item.sku_code,
                    warehouse_id=grn.warehouse_id,
                    quantity=item.damaged_quantity,
                    reference_number=grn.grn_number,
                    user=user,
                    reason=f'GRN {grn.grn_number} damaged items'
                )

        grn.status = GRNStatus.POSTED
        grn.posted_date = datetime.utcnow()

        self._log_status_change(grn_id, GRNStatus.APPROVED.value, GRNStatus.POSTED.value, user, 'GRN posted to inventory')
        self.db.commit()

        return {'success': True, 'grn_id': grn_id, 'items_posted': len(grn.items)}

    def reject_grn(self, grn_id, rejection_reason='', user='system'):
        """Reject GRN"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        if not grn:
            return {'success': False, 'error': 'GRN not found'}

        old_status = grn.status.value if grn.status else None
        grn.status = GRNStatus.REJECTED
        grn.rejection_reason = rejection_reason

        self._log_status_change(grn_id, old_status, GRNStatus.REJECTED.value, user, rejection_reason)
        self.db.commit()

        return {'success': True}

    def cancel_grn(self, grn_id, reason='', user='system'):
        """Cancel GRN"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        if not grn or grn.status == GRNStatus.POSTED:
            return {'success': False, 'error': 'Cannot cancel posted GRN'}

        old_status = grn.status.value if grn.status else None
        grn.status = GRNStatus.CANCELLED

        self._log_status_change(grn_id, old_status, GRNStatus.CANCELLED.value, user, f'Cancelled: {reason}')
        self.db.commit()

        return {'success': True}

    # =====================================================================
    # GRN SEARCH & RETRIEVAL
    # =====================================================================

    def get_grn(self, grn_id):
        """Get GRN details"""
        grn = self.db.query(GRNModel).filter_by(id=grn_id).first()
        return grn.to_dict() if grn else None

    def search_grns(self, filters=None, limit=100):
        """Search GRNs"""
        query = self.db.query(GRNModel)

        if not filters:
            filters = {}

        if filters.get('grn_number'):
            query = query.filter(GRNModel.grn_number.ilike(f"%{filters['grn_number']}%"))

        if filters.get('status'):
            query = query.filter_by(status=filters['status'])

        if filters.get('supplier'):
            query = query.filter(GRNModel.supplier_name.ilike(f"%{filters['supplier']}%"))

        if filters.get('warehouse_id'):
            query = query.filter_by(warehouse_id=filters['warehouse_id'])

        grns = query.order_by(desc(GRNModel.created_at)).limit(limit).all()
        return [g.to_dict() for g in grns]

    def get_grn_history(self, grn_id):
        """Get GRN status history"""
        history = self.db.query(GRNHistory).filter_by(grn_id=grn_id).order_by(
            desc(GRNHistory.created_at)
        ).all()

        return [{
            'timestamp': h.created_at.isoformat() if h.created_at else None,
            'old_status': h.old_status,
            'new_status': h.new_status,
            'changed_by': h.changed_by,
            'reason': h.change_reason
        } for h in history]

    # =====================================================================
    # STATISTICS
    # =====================================================================

    def get_grn_stats(self):
        """Get GRN statistics"""
        total = self.db.query(GRNModel).count()
        draft = self.db.query(GRNModel).filter_by(status=GRNStatus.DRAFT).count()
        pending = self.db.query(GRNModel).filter(
            GRNModel.status.in_([GRNStatus.SUBMITTED, GRNStatus.INSPECTION])
        ).count()
        approved = self.db.query(GRNModel).filter_by(status=GRNStatus.APPROVED).count()
        posted = self.db.query(GRNModel).filter_by(status=GRNStatus.POSTED).count()

        return {
            'total': total,
            'draft': draft,
            'pending': pending,
            'approved': approved,
            'posted': posted
        }

    # =====================================================================
    # INTERNAL HELPERS
    # =====================================================================

    def _log_status_change(self, grn_id, old_status, new_status, user, reason):
        """Log GRN status change"""
        history = GRNHistory(
            grn_id=grn_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            change_reason=reason
        )
        self.db.add(history)
        self.db.commit()
