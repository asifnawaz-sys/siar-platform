#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fulfillment Engine - Picking, Packing, Dispatch
================================================
Complete fulfillment workflow for order processing.
Handles picking lists, packing, shipment creation, multi-carrier support.
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
import json

Base = declarative_base()


class PickingStatus(enum.Enum):
    """Picking list status"""
    DRAFT = "Draft"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class PackingStatus(enum.Enum):
    """Packing list status"""
    DRAFT = "Draft"
    IN_PROGRESS = "In Progress"
    QC_PENDING = "QC Pending"
    QC_PASSED = "QC Passed"
    QC_FAILED = "QC Failed"
    PACKED = "Packed"
    CANCELLED = "Cancelled"


class ShipmentStatus(enum.Enum):
    """Shipment status"""
    DRAFT = "Draft"
    CREATED = "Created"
    LABEL_GENERATED = "Label Generated"
    PICKED_UP = "Picked Up"
    IN_TRANSIT = "In Transit"
    OUT_FOR_DELIVERY = "Out For Delivery"
    DELIVERED = "Delivered"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class CarrierType(enum.Enum):
    """Shipping carrier types"""
    USPS = "USPS"
    UPS = "UPS"
    FEDEX = "FedEx"
    DHL = "DHL"
    AMAZON = "Amazon Logistics"
    LOCAL = "Local Courier"
    MANUAL = "Manual"


class PickingList(Base):
    """Picking list master"""
    __tablename__ = 'picking_lists'

    id = Column(Integer, primary_key=True)
    picking_number = Column(String(100), unique=True, nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)

    status = Column(Enum(PickingStatus), default=PickingStatus.DRAFT, index=True)
    assigned_to = Column(String(100))  # Picker staff name

    order_count = Column(Integer, default=0)
    item_count = Column(Integer, default=0)
    picked_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    assigned_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    notes = Column(Text)
    created_by = Column(String(100))

    items = relationship('PickingListItem', back_populates='picking_list', cascade='all, delete-orphan')
    history = relationship('PickingHistory', back_populates='picking_list', cascade='all, delete-orphan')


class PickingListItem(Base):
    """Individual item in picking list"""
    __tablename__ = 'picking_list_items'

    id = Column(Integer, primary_key=True)
    picking_list_id = Column(Integer, ForeignKey('picking_lists.id'), nullable=False)
    order_item_id = Column(Integer, ForeignKey('order_items.id'))
    order_id = Column(Integer, ForeignKey('orders.id'))

    sku_code = Column(String(100), nullable=False)
    product_name = Column(String(255))
    quantity_needed = Column(Integer, nullable=False)
    quantity_picked = Column(Integer, default=0)

    bin_location = Column(String(50))  # Warehouse bin location
    picked_at = Column(DateTime)
    picked_by = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)

    picking_list = relationship('PickingList', back_populates='items')


class PickingHistory(Base):
    """Picking list status history"""
    __tablename__ = 'picking_history'

    id = Column(Integer, primary_key=True)
    picking_list_id = Column(Integer, ForeignKey('picking_lists.id'), nullable=False)
    old_status = Column(String(50))
    new_status = Column(String(50), nullable=False)
    changed_by = Column(String(100))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    picking_list = relationship('PickingList', back_populates='history')


class PackingList(Base):
    """Packing list master"""
    __tablename__ = 'packing_lists'

    id = Column(Integer, primary_key=True)
    packing_number = Column(String(100), unique=True, nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)
    picking_list_id = Column(Integer, ForeignKey('picking_lists.id'))

    status = Column(Enum(PackingStatus), default=PackingStatus.DRAFT, index=True)
    assigned_to = Column(String(100))  # Packer staff name

    order_count = Column(Integer, default=0)
    item_count = Column(Integer, default=0)

    box_count = Column(Integer, default=0)
    total_weight = Column(Float, default=0.0)  # kg
    total_volume = Column(Float, default=0.0)  # cubic cm

    qc_status = Column(String(50))  # PENDING, PASSED, FAILED
    qc_checked_by = Column(String(100))
    qc_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    qc_at = Column(DateTime)
    completed_at = Column(DateTime)

    notes = Column(Text)
    created_by = Column(String(100))

    items = relationship('PackingListItem', back_populates='packing_list', cascade='all, delete-orphan')
    boxes = relationship('PackedBox', back_populates='packing_list', cascade='all, delete-orphan')
    history = relationship('PackingHistory', back_populates='packing_list', cascade='all, delete-orphan')


class PackingListItem(Base):
    """Individual item in packing list"""
    __tablename__ = 'packing_list_items'

    id = Column(Integer, primary_key=True)
    packing_list_id = Column(Integer, ForeignKey('packing_lists.id'), nullable=False)
    order_item_id = Column(Integer, ForeignKey('order_items.id'))
    order_id = Column(Integer, ForeignKey('orders.id'))

    sku_code = Column(String(100), nullable=False)
    product_name = Column(String(255))
    quantity_needed = Column(Integer, nullable=False)
    quantity_packed = Column(Integer, default=0)

    packed_at = Column(DateTime)
    packed_by = Column(String(100))
    box_number = Column(Integer)  # Which box this item is in

    created_at = Column(DateTime, default=datetime.utcnow)

    packing_list = relationship('PackingList', back_populates='items')


class PackedBox(Base):
    """Individual packed box/shipment unit"""
    __tablename__ = 'packed_boxes'

    id = Column(Integer, primary_key=True)
    packing_list_id = Column(Integer, ForeignKey('packing_lists.id'), nullable=False)
    box_number = Column(Integer, nullable=False)

    length = Column(Float)  # cm
    width = Column(Float)   # cm
    height = Column(Float)  # cm
    weight = Column(Float)  # kg
    volume = Column(Float)  # cubic cm

    contents = Column(JSON)  # [{sku, quantity}, ...]

    created_at = Column(DateTime, default=datetime.utcnow)

    packing_list = relationship('PackingList', back_populates='boxes')
    shipment = relationship('Shipment', uselist=False, back_populates='box')


class Shipment(Base):
    """Shipment/Order for delivery"""
    __tablename__ = 'shipments'

    id = Column(Integer, primary_key=True)
    shipment_number = Column(String(100), unique=True, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)
    packed_box_id = Column(Integer, ForeignKey('packed_boxes.id'))

    status = Column(Enum(ShipmentStatus), default=ShipmentStatus.DRAFT, index=True)

    carrier = Column(Enum(CarrierType), nullable=False)
    tracking_number = Column(String(100), index=True)
    label_url = Column(String(500))

    recipient_name = Column(String(255))
    recipient_email = Column(String(255))
    recipient_phone = Column(String(20))

    shipping_address = Column(JSON)  # {street, city, state, zip, country}
    weight = Column(Float)  # kg
    dimensions = Column(JSON)  # {length, width, height}

    shipping_cost = Column(Float, default=0.0)
    estimated_delivery = Column(DateTime)

    picked_up_at = Column(DateTime)
    delivered_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    box = relationship('PackedBox', back_populates='shipment')
    history = relationship('ShipmentHistory', back_populates='shipment', cascade='all, delete-orphan')


class ShipmentHistory(Base):
    """Shipment status tracking"""
    __tablename__ = 'shipment_history'

    id = Column(Integer, primary_key=True)
    shipment_id = Column(Integer, ForeignKey('shipments.id'), nullable=False)
    old_status = Column(String(50))
    new_status = Column(String(50), nullable=False)
    status_detail = Column(String(255))  # e.g., "In Transit to Distribution Center"
    location = Column(String(255))  # Current location
    changed_by = Column(String(100))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    shipment = relationship('Shipment', back_populates='history')


class PackingHistory(Base):
    """Packing list status history"""
    __tablename__ = 'packing_list_history'

    id = Column(Integer, primary_key=True)
    packing_list_id = Column(Integer, ForeignKey('packing_lists.id'), nullable=False)
    old_status = Column(String(50))
    new_status = Column(String(50), nullable=False)
    changed_by = Column(String(100))
    change_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    packing_list = relationship('PackingList', back_populates='history')


class FulfillmentEngine:
    """Complete fulfillment workflow management"""

    def __init__(self, db_session, inventory_engine=None):
        self.db = db_session
        self.inventory = inventory_engine

    # =====================================================================
    # PICKING LIST MANAGEMENT
    # =====================================================================

    def create_picking_list(self, warehouse_id, orders, user='system'):
        """Create picking list from orders"""
        picking_list = PickingList(
            picking_number=self._generate_picking_number(),
            warehouse_id=warehouse_id,
            order_count=len(orders),
            created_by=user
        )

        self.db.add(picking_list)
        self.db.flush()

        item_count = 0
        for order_id in orders:
            # Get order items
            from .models import OrderItem
            items = self.db.query(OrderItem).filter_by(order_id=order_id).all()

            for item in items:
                picking_item = PickingListItem(
                    picking_list_id=picking_list.id,
                    order_item_id=item.id,
                    order_id=order_id,
                    sku_code=item.sku_code,
                    product_name=item.product_name,
                    quantity_needed=item.quantity
                )
                self.db.add(picking_item)
                item_count += 1

        picking_list.item_count = item_count
        self.db.commit()
        self._log_picking_status_change(picking_list.id, None, PickingStatus.DRAFT.value, user, 'Picking list created')

        return {'success': True, 'picking_list_id': picking_list.id, 'picking_number': picking_list.picking_number}

    def assign_picking_list(self, picking_list_id, assigned_to, user='system'):
        """Assign picking list to staff"""
        picking_list = self.db.query(PickingList).filter_by(id=picking_list_id).first()
        if not picking_list:
            return {'success': False, 'error': 'Picking list not found'}

        picking_list.status = PickingStatus.ASSIGNED
        picking_list.assigned_to = assigned_to
        picking_list.assigned_at = datetime.utcnow()

        self._log_picking_status_change(picking_list_id, PickingStatus.DRAFT.value, PickingStatus.ASSIGNED.value, user, f'Assigned to {assigned_to}')
        self.db.commit()

        return {'success': True}

    def start_picking(self, picking_list_id, user='system'):
        """Start picking operation"""
        picking_list = self.db.query(PickingList).filter_by(id=picking_list_id).first()
        if not picking_list:
            return {'success': False, 'error': 'Picking list not found'}

        picking_list.status = PickingStatus.IN_PROGRESS
        picking_list.started_at = datetime.utcnow()

        self._log_picking_status_change(picking_list_id, PickingStatus.ASSIGNED.value, PickingStatus.IN_PROGRESS.value, user, 'Picking started')
        self.db.commit()

        return {'success': True}

    def record_picked_item(self, picking_list_id, picking_item_id, quantity_picked, user='system'):
        """Record item pick"""
        picking_item = self.db.query(PickingListItem).filter_by(
            id=picking_item_id,
            picking_list_id=picking_list_id
        ).first()

        if not picking_item:
            return {'success': False, 'error': 'Item not found'}

        if quantity_picked > picking_item.quantity_needed:
            return {'success': False, 'error': 'Quantity exceeds needed'}

        picking_item.quantity_picked = quantity_picked
        picking_item.picked_at = datetime.utcnow()
        picking_item.picked_by = user

        # Update picking list progress
        picking_list = self.db.query(PickingList).filter_by(id=picking_list_id).first()
        picking_list.picked_count = self.db.query(PickingListItem).filter_by(
            picking_list_id=picking_list_id
        ).filter(PickingListItem.quantity_picked > 0).count()

        self.db.commit()

        return {'success': True, 'picked_count': picking_list.picked_count, 'total_count': picking_list.item_count}

    def complete_picking(self, picking_list_id, user='system'):
        """Complete picking list"""
        picking_list = self.db.query(PickingList).filter_by(id=picking_list_id).first()
        if not picking_list:
            return {'success': False, 'error': 'Picking list not found'}

        # Verify all items picked
        unpicked = self.db.query(PickingListItem).filter_by(picking_list_id=picking_list_id).filter(
            PickingListItem.quantity_picked == 0
        ).count()

        if unpicked > 0:
            return {'success': False, 'error': f'{unpicked} items not yet picked'}

        picking_list.status = PickingStatus.COMPLETED
        picking_list.completed_at = datetime.utcnow()

        self._log_picking_status_change(picking_list_id, PickingStatus.IN_PROGRESS.value, PickingStatus.COMPLETED.value, user, 'Picking completed')
        self.db.commit()

        return {'success': True, 'picked_count': picking_list.picked_count}

    # =====================================================================
    # PACKING LIST MANAGEMENT
    # =====================================================================

    def create_packing_list(self, picking_list_id, warehouse_id, user='system'):
        """Create packing list from picking list"""
        picking_list = self.db.query(PickingList).filter_by(id=picking_list_id).first()
        if not picking_list:
            return {'success': False, 'error': 'Picking list not found'}

        packing_list = PackingList(
            packing_number=self._generate_packing_number(),
            warehouse_id=warehouse_id,
            picking_list_id=picking_list_id,
            order_count=picking_list.order_count,
            item_count=picking_list.item_count,
            created_by=user
        )

        self.db.add(packing_list)
        self.db.flush()

        # Copy items from picking list
        picking_items = self.db.query(PickingListItem).filter_by(picking_list_id=picking_list_id).all()
        for p_item in picking_items:
            packing_item = PackingListItem(
                packing_list_id=packing_list.id,
                order_item_id=p_item.order_item_id,
                order_id=p_item.order_id,
                sku_code=p_item.sku_code,
                product_name=p_item.product_name,
                quantity_needed=p_item.quantity_picked
            )
            self.db.add(packing_item)

        self.db.commit()
        self._log_packing_status_change(packing_list.id, None, PackingStatus.DRAFT.value, user, 'Packing list created')

        return {'success': True, 'packing_list_id': packing_list.id, 'packing_number': packing_list.packing_number}

    def start_packing(self, packing_list_id, assigned_to, user='system'):
        """Start packing operation"""
        packing_list = self.db.query(PackingList).filter_by(id=packing_list_id).first()
        if not packing_list:
            return {'success': False, 'error': 'Packing list not found'}

        packing_list.status = PackingStatus.IN_PROGRESS
        packing_list.assigned_to = assigned_to
        packing_list.started_at = datetime.utcnow()

        self._log_packing_status_change(packing_list_id, PackingStatus.DRAFT.value, PackingStatus.IN_PROGRESS.value, user, f'Packing started by {assigned_to}')
        self.db.commit()

        return {'success': True}

    def record_packed_item(self, packing_list_id, packing_item_id, quantity_packed, box_number, user='system'):
        """Record item packed into box"""
        packing_item = self.db.query(PackingListItem).filter_by(
            id=packing_item_id,
            packing_list_id=packing_list_id
        ).first()

        if not packing_item:
            return {'success': False, 'error': 'Item not found'}

        packing_item.quantity_packed = quantity_packed
        packing_item.packed_at = datetime.utcnow()
        packing_item.packed_by = user
        packing_item.box_number = box_number

        self.db.commit()

        return {'success': True}

    def create_packed_box(self, packing_list_id, box_number, length, width, height, weight, contents):
        """Record packed box dimensions and contents"""
        packing_list = self.db.query(PackingList).filter_by(id=packing_list_id).first()
        if not packing_list:
            return {'success': False, 'error': 'Packing list not found'}

        volume = (length * width * height) / 1000  # Convert cm³ to liters for storage

        packed_box = PackedBox(
            packing_list_id=packing_list_id,
            box_number=box_number,
            length=length,
            width=width,
            height=height,
            weight=weight,
            volume=volume,
            contents=contents
        )

        self.db.add(packed_box)

        # Update packing list totals
        packing_list.box_count += 1
        packing_list.total_weight += weight
        packing_list.total_volume += volume

        self.db.commit()

        return {'success': True, 'box_id': packed_box.id}

    def complete_packing(self, packing_list_id, user='system'):
        """Mark packing as complete, ready for QC"""
        packing_list = self.db.query(PackingList).filter_by(id=packing_list_id).first()
        if not packing_list:
            return {'success': False, 'error': 'Packing list not found'}

        # Verify all items packed
        unpacked = self.db.query(PackingListItem).filter_by(packing_list_id=packing_list_id).filter(
            PackingListItem.quantity_packed == 0
        ).count()

        if unpacked > 0:
            return {'success': False, 'error': f'{unpacked} items not yet packed'}

        packing_list.status = PackingStatus.QC_PENDING
        self._log_packing_status_change(packing_list_id, PackingStatus.IN_PROGRESS.value, PackingStatus.QC_PENDING.value, user, 'Packing completed, awaiting QC')
        self.db.commit()

        return {'success': True, 'box_count': packing_list.box_count}

    def perform_quality_check(self, packing_list_id, qc_passed, qc_notes, qc_by='system'):
        """Perform quality check on packing list"""
        packing_list = self.db.query(PackingList).filter_by(id=packing_list_id).first()
        if not packing_list:
            return {'success': False, 'error': 'Packing list not found'}

        packing_list.qc_status = 'PASSED' if qc_passed else 'FAILED'
        packing_list.qc_checked_by = qc_by
        packing_list.qc_notes = qc_notes
        packing_list.qc_at = datetime.utcnow()

        if qc_passed:
            packing_list.status = PackingStatus.QC_PASSED
            self._log_packing_status_change(packing_list_id, PackingStatus.QC_PENDING.value, PackingStatus.QC_PASSED.value, qc_by, f'QC PASSED: {qc_notes}')
        else:
            packing_list.status = PackingStatus.QC_FAILED
            self._log_packing_status_change(packing_list_id, PackingStatus.QC_PENDING.value, PackingStatus.QC_FAILED.value, qc_by, f'QC FAILED: {qc_notes}')

        self.db.commit()

        return {'success': True, 'qc_status': packing_list.qc_status}

    # =====================================================================
    # SHIPMENT MANAGEMENT
    # =====================================================================

    def create_shipment(self, order_id, carrier, weight, dimensions, shipping_cost=0.0, user='system'):
        """Create shipment for order"""
        shipment = Shipment(
            shipment_number=self._generate_shipment_number(),
            order_id=order_id,
            carrier=carrier,
            weight=weight,
            dimensions=dimensions,
            shipping_cost=shipping_cost,
            created_by=user
        )

        self.db.add(shipment)
        self.db.flush()

        self._log_shipment_status_change(shipment.id, None, ShipmentStatus.DRAFT.value, user, 'Shipment created')
        self.db.commit()

        return {'success': True, 'shipment_id': shipment.id, 'shipment_number': shipment.shipment_number}

    def assign_tracking_number(self, shipment_id, tracking_number, label_url='', user='system'):
        """Assign tracking number to shipment"""
        shipment = self.db.query(Shipment).filter_by(id=shipment_id).first()
        if not shipment:
            return {'success': False, 'error': 'Shipment not found'}

        shipment.tracking_number = tracking_number
        shipment.label_url = label_url
        shipment.status = ShipmentStatus.LABEL_GENERATED
        shipment.estimated_delivery = datetime.utcnow() + timedelta(days=3)  # Default 3-day delivery

        self._log_shipment_status_change(shipment_id, ShipmentStatus.DRAFT.value, ShipmentStatus.LABEL_GENERATED.value, user, f'Tracking: {tracking_number}')
        self.db.commit()

        return {'success': True, 'tracking_number': tracking_number}

    def mark_picked_up(self, shipment_id, user='system'):
        """Mark shipment as picked up by carrier"""
        shipment = self.db.query(Shipment).filter_by(id=shipment_id).first()
        if not shipment:
            return {'success': False, 'error': 'Shipment not found'}

        shipment.status = ShipmentStatus.PICKED_UP
        shipment.picked_up_at = datetime.utcnow()

        self._log_shipment_status_change(shipment_id, ShipmentStatus.LABEL_GENERATED.value, ShipmentStatus.PICKED_UP.value, user, 'Picked up by carrier')
        self.db.commit()

        return {'success': True}

    def update_shipment_status(self, shipment_id, new_status, status_detail='', location='', user='system'):
        """Update shipment tracking status"""
        shipment = self.db.query(Shipment).filter_by(id=shipment_id).first()
        if not shipment:
            return {'success': False, 'error': 'Shipment not found'}

        old_status = shipment.status.value

        if new_status == 'IN_TRANSIT':
            shipment.status = ShipmentStatus.IN_TRANSIT
        elif new_status == 'OUT_FOR_DELIVERY':
            shipment.status = ShipmentStatus.OUT_FOR_DELIVERY
        elif new_status == 'DELIVERED':
            shipment.status = ShipmentStatus.DELIVERED
            shipment.delivered_at = datetime.utcnow()
        elif new_status == 'FAILED':
            shipment.status = ShipmentStatus.FAILED

        self._log_shipment_status_change(shipment_id, old_status, new_status, user, f'{status_detail} - {location}')
        self.db.commit()

        return {'success': True, 'status': new_status}

    def get_shipment_tracking(self, shipment_id):
        """Get shipment tracking information"""
        shipment = self.db.query(Shipment).filter_by(id=shipment_id).first()
        if not shipment:
            return None

        history = self.db.query(ShipmentHistory).filter_by(shipment_id=shipment_id).order_by(
            ShipmentHistory.created_at.asc()
        ).all()

        return {
            'shipment_number': shipment.shipment_number,
            'tracking_number': shipment.tracking_number,
            'carrier': shipment.carrier.value if shipment.carrier else None,
            'current_status': shipment.status.value if shipment.status else None,
            'label_url': shipment.label_url,
            'estimated_delivery': shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
            'delivered_at': shipment.delivered_at.isoformat() if shipment.delivered_at else None,
            'timeline': [
                {
                    'timestamp': h.created_at.isoformat() if h.created_at else None,
                    'status': h.new_status,
                    'detail': h.status_detail,
                    'location': h.location
                }
                for h in history
            ]
        }

    # =====================================================================
    # INTERNAL HELPERS
    # =====================================================================

    def _generate_picking_number(self):
        """Generate unique picking number"""
        import uuid
        return f"PK-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    def _generate_packing_number(self):
        """Generate unique packing number"""
        import uuid
        return f"PK-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    def _generate_shipment_number(self):
        """Generate unique shipment number"""
        import uuid
        return f"SHP-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    def _log_picking_status_change(self, picking_list_id, old_status, new_status, user, reason):
        """Log picking list status change"""
        history = PickingHistory(
            picking_list_id=picking_list_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            change_reason=reason
        )
        self.db.add(history)
        self.db.commit()

    def _log_packing_status_change(self, packing_list_id, old_status, new_status, user, reason):
        """Log packing list status change"""
        history = PackingHistory(
            packing_list_id=packing_list_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            change_reason=reason
        )
        self.db.add(history)
        self.db.commit()

    def _log_shipment_status_change(self, shipment_id, old_status, new_status, user, reason):
        """Log shipment status change"""
        history = ShipmentHistory(
            shipment_id=shipment_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            change_reason=reason
        )
        self.db.add(history)
        self.db.commit()
