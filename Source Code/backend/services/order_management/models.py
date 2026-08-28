#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Management + SKU Inventory Database Models
================================================
Comprehensive models for order processing and inventory management
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

# =====================================================================
# WAREHOUSE MODELS
# =====================================================================

class Warehouse(Base):
    __tablename__ = 'warehouses'

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    address = Column(Text)
    contact = Column(String(50))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sku_inventory = relationship('SKUInventory', back_populates='warehouse')
    orders = relationship('Order', back_populates='warehouse')
    movements = relationship('InventoryMovement', back_populates='warehouse')

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'location': self.location,
            'address': self.address,
            'contact': self.contact,
            'is_active': self.is_active
        }


# =====================================================================
# SKU & INVENTORY MODELS
# =====================================================================

class SKUMaster(Base):
    __tablename__ = 'sku_master'

    id = Column(Integer, primary_key=True)
    sku = Column(String(100), unique=True, nullable=False, index=True)
    product_name = Column(String(255), nullable=False)
    variant = Column(String(255))
    size = Column(String(50))
    color = Column(String(50))
    brand = Column(String(100))
    category = Column(String(100))
    unit_cost = Column(Float, default=0.0)
    retail_price = Column(Float, default=0.0)
    barcode = Column(String(100), unique=True, nullable=True)
    is_active = Column(Boolean, default=True)
    reorder_level = Column(Integer, default=10)
    max_stock = Column(Integer, default=1000)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    inventory = relationship('SKUInventory', back_populates='sku_master', cascade='all, delete-orphan')
    order_items = relationship('OrderItem', back_populates='sku_master')
    movements = relationship('InventoryMovement', back_populates='sku_master')

    def to_dict(self):
        return {
            'id': self.id,
            'sku': self.sku,
            'product_name': self.product_name,
            'variant': self.variant,
            'size': self.size,
            'color': self.color,
            'brand': self.brand,
            'category': self.category,
            'unit_cost': self.unit_cost,
            'retail_price': self.retail_price,
            'barcode': self.barcode,
            'reorder_level': self.reorder_level,
            'max_stock': self.max_stock
        }


class SKUInventory(Base):
    __tablename__ = 'sku_inventory'

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey('sku_master.id'), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)

    physical_stock = Column(Integer, default=0)
    reserved_stock = Column(Integer, default=0)
    incoming_stock = Column(Integer, default=0)
    damaged_stock = Column(Integer, default=0)
    returned_stock = Column(Integer, default=0)

    available_to_sell = Column(Integer, default=0)
    inventory_value = Column(Float, default=0.0)

    last_counted = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sku_master = relationship('SKUMaster', back_populates='inventory')
    warehouse = relationship('Warehouse', back_populates='sku_inventory')

    @property
    def available_stock(self):
        """Available Stock = Physical Stock - Reserved Stock"""
        return max(0, self.physical_stock - self.reserved_stock)

    def to_dict(self):
        sku = self.sku_master
        return {
            'id': self.id,
            'sku': sku.sku if sku else None,
            'product_name': sku.product_name if sku else None,
            'warehouse': self.warehouse.name if self.warehouse else None,
            'physical_stock': self.physical_stock,
            'reserved_stock': self.reserved_stock,
            'incoming_stock': self.incoming_stock,
            'damaged_stock': self.damaged_stock,
            'returned_stock': self.returned_stock,
            'available_stock': self.available_stock,
            'available_to_sell': self.available_to_sell,
            'inventory_value': self.inventory_value
        }


# =====================================================================
# ORDER MODELS
# =====================================================================

class OrderStatus(enum.Enum):
    NEW = "New"
    CONFIRMED = "Confirmed"
    PAYMENT_VERIFIED = "Payment Verified"
    INVENTORY_RESERVED = "Inventory Reserved"
    PICKING = "Picking"
    PICKED = "Picked"
    PACKING = "Packing"
    PACKED = "Packed"
    READY_FOR_DISPATCH = "Ready for Dispatch"
    DISPATCHED = "Dispatched"
    DELIVERED = "Delivered"
    CANCELLED = "Cancelled"
    ON_HOLD = "On Hold"
    FAILED = "Failed"
    RETURNED = "Returned"
    PARTIALLY_RETURNED = "Partially Returned"
    REFUNDED = "Refunded"
    PARTIALLY_REFUNDED = "Partially Refunded"


class PaymentStatus(enum.Enum):
    PENDING = "Pending"
    AUTHORIZED = "Authorized"
    PAID = "Paid"
    FAILED = "Failed"
    CANCELLED = "Cancelled"
    REFUNDED = "Refunded"


class Order(Base):
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True)
    order_number = Column(String(100), unique=True, nullable=False, index=True)
    marketplace = Column(String(50), default='Direct', index=True)
    marketplace_order_id = Column(String(100), nullable=True, index=True)

    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255))
    customer_phone = Column(String(50))

    shipping_address = Column(Text)
    billing_address = Column(Text)

    order_status = Column(Enum(OrderStatus), default=OrderStatus.NEW, index=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, index=True)

    subtotal = Column(Float, default=0.0)
    shipping_cost = Column(Float, default=0.0)
    tax = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    warehouse_id = Column(Integer, ForeignKey('warehouses.id'))
    priority = Column(Integer, default=0)

    notes = Column(Text)
    internal_comments = Column(Text)

    tracking_number = Column(String(100))
    shipped_date = Column(DateTime)
    delivered_date = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    ordered_at = Column(DateTime, default=datetime.utcnow)

    warehouse = relationship('Warehouse', back_populates='orders')
    items = relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    history = relationship('OrderHistory', back_populates='order', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'order_number': self.order_number,
            'marketplace': self.marketplace,
            'customer_name': self.customer_name,
            'customer_email': self.customer_email,
            'order_status': self.order_status.value if self.order_status else None,
            'payment_status': self.payment_status.value if self.payment_status else None,
            'total': self.total,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'items': [item.to_dict() for item in self.items]
        }


class OrderItem(Base):
    __tablename__ = 'order_items'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, index=True)
    sku_id = Column(Integer, ForeignKey('sku_master.id'), nullable=False, index=True)

    sku_code = Column(String(100), nullable=False)
    product_name = Column(String(255))
    quantity_ordered = Column(Integer, nullable=False)
    quantity_picked = Column(Integer, default=0)
    quantity_packed = Column(Integer, default=0)
    quantity_shipped = Column(Integer, default=0)
    quantity_returned = Column(Integer, default=0)

    unit_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship('Order', back_populates='items')
    sku_master = relationship('SKUMaster', back_populates='order_items')

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'sku_code': self.sku_code,
            'product_name': self.product_name,
            'quantity_ordered': self.quantity_ordered,
            'quantity_picked': self.quantity_picked,
            'quantity_shipped': self.quantity_shipped,
            'unit_price': self.unit_price,
            'line_total': self.line_total
        }


class OrderHistory(Base):
    __tablename__ = 'order_history'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, index=True)

    old_status = Column(String(100))
    new_status = Column(String(100), nullable=False)

    changed_by = Column(String(100))
    change_reason = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    order = relationship('Order', back_populates='history')


# =====================================================================
# INVENTORY MOVEMENT MODELS
# =====================================================================

class MovementType(enum.Enum):
    GRN = "GRN"
    SALES_ORDER = "Sales Order"
    RESERVATION = "Reservation"
    CANCELLATION = "Cancellation"
    RETURN = "Return"
    REFUND = "Refund"
    ADJUSTMENT = "Adjustment"
    TRANSFER = "Transfer"
    DAMAGE = "Damage"
    LOST_STOCK = "Lost Stock"
    MARKETPLACE_SYNC = "Marketplace Sync"
    MANUAL_ADJUSTMENT = "Manual Adjustment"


class InventoryMovement(Base):
    __tablename__ = 'inventory_movements'

    id = Column(Integer, primary_key=True)
    sku_id = Column(Integer, ForeignKey('sku_master.id'), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False, index=True)

    movement_type = Column(Enum(MovementType), nullable=False, index=True)
    reference_number = Column(String(100), index=True)

    quantity_before = Column(Integer, nullable=False)
    quantity_change = Column(Integer, nullable=False)
    quantity_after = Column(Integer, nullable=False)

    user = Column(String(100))
    source = Column(String(100))
    reason = Column(Text)
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    sku_master = relationship('SKUMaster', back_populates='movements')
    warehouse = relationship('Warehouse', back_populates='movements')

    def to_dict(self):
        sku = self.sku_master
        return {
            'id': self.id,
            'sku': sku.sku if sku else None,
            'warehouse': self.warehouse.name if self.warehouse else None,
            'movement_type': self.movement_type.value if self.movement_type else None,
            'reference_number': self.reference_number,
            'quantity_before': self.quantity_before,
            'quantity_change': self.quantity_change,
            'quantity_after': self.quantity_after,
            'user': self.user,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class InventoryReservation(Base):
    __tablename__ = 'inventory_reservations'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey('order_items.id'), nullable=False, index=True)
    sku_id = Column(Integer, ForeignKey('sku_master.id'), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey('warehouses.id'), nullable=False)

    quantity_reserved = Column(Integer, nullable=False)
    quantity_picked = Column(Integer, default=0)
    quantity_cancelled = Column(Integer, default=0)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'sku_id': self.sku_id,
            'quantity_reserved': self.quantity_reserved,
            'quantity_picked': self.quantity_picked,
            'is_active': self.is_active
        }


# =====================================================================
# CUSTOMER MODEL
# =====================================================================

class Customer(Base):
    __tablename__ = 'customers'

    id = Column(Integer, primary_key=True)
    customer_code = Column(String(100), unique=True, nullable=False, index=True)

    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone = Column(String(50))

    default_shipping_address = Column(Text)
    default_billing_address = Column(Text)

    total_orders = Column(Integer, default=0)
    total_spent = Column(Float, default=0.0)
    total_returns = Column(Integer, default=0)
    total_cancellations = Column(Integer, default=0)

    preferred_marketplace = Column(String(50))
    notes = Column(Text)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'customer_code': self.customer_code,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'total_orders': self.total_orders,
            'total_spent': self.total_spent,
            'total_returns': self.total_returns
        }
