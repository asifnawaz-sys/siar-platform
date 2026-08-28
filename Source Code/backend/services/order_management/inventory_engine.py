#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inventory Engine - Core Stock Management Logic
==============================================
Handles all inventory calculations, reservations, deductions, and movements.
Follows ERP principles (SAP-style) with complete audit trail.
"""

from datetime import datetime
from sqlalchemy import create_database, Column
from .models import (
    SKUInventory, SKUMaster, InventoryMovement, InventoryReservation,
    MovementType, Order, OrderItem, OrderStatus, PaymentStatus
)


class InventoryEngine:
    """
    Core inventory management engine.
    All stock movements must go through this engine to maintain audit trail.
    """

    def __init__(self, db_session):
        self.db = db_session

    # =====================================================================
    # INVENTORY RETRIEVAL & CALCULATION
    # =====================================================================

    def get_sku_inventory(self, sku_code, warehouse_id=None):
        """Get inventory for a SKU"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return None

        if warehouse_id:
            return self.db.query(SKUInventory).filter_by(
                sku_id=sku.id, warehouse_id=warehouse_id
            ).first()
        else:
            return self.db.query(SKUInventory).filter_by(sku_id=sku.id).all()

    def get_available_stock(self, sku_code, warehouse_id):
        """Available Stock = Physical Stock - Reserved Stock"""
        inventory = self.get_sku_inventory(sku_code, warehouse_id)
        if not inventory:
            return 0
        return max(0, inventory.physical_stock - inventory.reserved_stock)

    def get_sku_total_inventory(self, sku_code):
        """Get total inventory across all warehouses"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return {'physical': 0, 'reserved': 0, 'available': 0}

        inventories = self.db.query(SKUInventory).filter_by(sku_id=sku.id).all()

        total_physical = sum(inv.physical_stock for inv in inventories)
        total_reserved = sum(inv.reserved_stock for inv in inventories)
        total_available = max(0, total_physical - total_reserved)

        return {
            'sku': sku_code,
            'physical_stock': total_physical,
            'reserved_stock': total_reserved,
            'available_stock': total_available,
            'warehouses': [inv.to_dict() for inv in inventories]
        }

    def is_in_stock(self, sku_code, quantity, warehouse_id):
        """Check if quantity is available in stock"""
        available = self.get_available_stock(sku_code, warehouse_id)
        return available >= quantity

    def check_multi_sku_availability(self, order_items, warehouse_id):
        """Check if all items in order can be fulfilled"""
        results = []
        for item in order_items:
            available = self.get_available_stock(item['sku_code'], warehouse_id)
            results.append({
                'sku_code': item['sku_code'],
                'requested': item['quantity'],
                'available': available,
                'can_fulfill': available >= item['quantity']
            })
        return results

    # =====================================================================
    # INVENTORY RESERVATION
    # =====================================================================

    def reserve_inventory(self, order_id, order_item_id, sku_code, quantity, warehouse_id, user='system'):
        """
        Reserve inventory for an order.
        Reduces available-to-sell without removing from physical stock.
        """
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return {'success': False, 'error': f'SKU {sku_code} not found'}

        if not self.is_in_stock(sku_code, quantity, warehouse_id):
            return {'success': False, 'error': f'Insufficient stock for {sku_code}'}

        inventory = self.db.query(SKUInventory).filter_by(
            sku_id=sku.id, warehouse_id=warehouse_id
        ).first()

        if not inventory:
            return {'success': False, 'error': f'Inventory record not found'}

        # Create reservation
        reservation = InventoryReservation(
            order_id=order_id,
            order_item_id=order_item_id,
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            quantity_reserved=quantity,
            is_active=True
        )

        # Increase reserved stock
        inventory.reserved_stock += quantity
        inventory.available_to_sell = max(0, inventory.physical_stock - inventory.reserved_stock)

        self.db.add(reservation)
        self.db.commit()

        # Log movement
        self._log_movement(
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            movement_type=MovementType.RESERVATION,
            reference_number=f"ORD-{order_id}",
            quantity_change=-quantity,
            quantity_before=inventory.physical_stock,
            quantity_after=inventory.physical_stock,
            user=user,
            reason=f'Order {order_id} item {order_item_id} reservation'
        )

        return {'success': True, 'reservation_id': reservation.id}

    def release_reservation(self, reservation_id, user='system'):
        """Release a reservation (e.g., when order is cancelled)"""
        reservation = self.db.query(InventoryReservation).filter_by(id=reservation_id).first()
        if not reservation or not reservation.is_active:
            return {'success': False, 'error': 'Reservation not found or already released'}

        inventory = self.db.query(SKUInventory).filter_by(
            sku_id=reservation.sku_id, warehouse_id=reservation.warehouse_id
        ).first()

        if inventory:
            # Decrease reserved stock
            inventory.reserved_stock = max(0, inventory.reserved_stock - reservation.quantity_reserved)
            inventory.available_to_sell = max(0, inventory.physical_stock - inventory.reserved_stock)

            self._log_movement(
                sku_id=reservation.sku_id,
                warehouse_id=reservation.warehouse_id,
                movement_type=MovementType.CANCELLATION,
                reference_number=f"RES-{reservation_id}",
                quantity_change=reservation.quantity_reserved,
                quantity_before=inventory.physical_stock,
                quantity_after=inventory.physical_stock,
                user=user,
                reason=f'Reservation {reservation_id} release'
            )

        reservation.is_active = False
        reservation.released_at = datetime.utcnow()
        self.db.commit()

        return {'success': True}

    # =====================================================================
    # INVENTORY ADJUSTMENT (GRN, Returns, Damage, etc.)
    # =====================================================================

    def add_stock(self, sku_code, warehouse_id, quantity, movement_type, reference_number, user='system', reason=''):
        """Add stock to inventory (GRN, returns, etc.)"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return {'success': False, 'error': f'SKU {sku_code} not found'}

        inventory = self.db.query(SKUInventory).filter_by(
            sku_id=sku.id, warehouse_id=warehouse_id
        ).first()

        if not inventory:
            return {'success': False, 'error': 'Inventory record not found'}

        quantity_before = inventory.physical_stock
        inventory.physical_stock += quantity
        inventory.available_to_sell = max(0, inventory.physical_stock - inventory.reserved_stock)
        inventory.inventory_value = inventory.physical_stock * (sku.unit_cost or 0)

        self._log_movement(
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
            reference_number=reference_number,
            quantity_change=quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.physical_stock,
            user=user,
            reason=reason
        )

        self.db.commit()

        return {
            'success': True,
            'sku': sku_code,
            'quantity_added': quantity,
            'new_stock': inventory.physical_stock
        }

    def deduct_stock(self, sku_code, warehouse_id, quantity, movement_type, reference_number, user='system', reason=''):
        """Deduct stock from inventory"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return {'success': False, 'error': f'SKU {sku_code} not found'}

        inventory = self.db.query(SKUInventory).filter_by(
            sku_id=sku.id, warehouse_id=warehouse_id
        ).first()

        if not inventory:
            return {'success': False, 'error': 'Inventory record not found'}

        if inventory.physical_stock < quantity:
            return {'success': False, 'error': 'Insufficient stock'}

        quantity_before = inventory.physical_stock
        inventory.physical_stock -= quantity
        inventory.available_to_sell = max(0, inventory.physical_stock - inventory.reserved_stock)
        inventory.inventory_value = inventory.physical_stock * (sku.unit_cost or 0)

        self._log_movement(
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
            reference_number=reference_number,
            quantity_change=-quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.physical_stock,
            user=user,
            reason=reason
        )

        self.db.commit()

        return {
            'success': True,
            'sku': sku_code,
            'quantity_deducted': quantity,
            'new_stock': inventory.physical_stock
        }

    # =====================================================================
    # DAMAGED & SPECIAL STOCK
    # =====================================================================

    def mark_damaged(self, sku_code, warehouse_id, quantity, reference_number, user='system', reason=''):
        """Mark inventory as damaged"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return {'success': False, 'error': f'SKU {sku_code} not found'}

        inventory = self.db.query(SKUInventory).filter_by(
            sku_id=sku.id, warehouse_id=warehouse_id
        ).first()

        if not inventory:
            return {'success': False, 'error': 'Inventory record not found'}

        inventory.physical_stock -= quantity
        inventory.damaged_stock += quantity
        inventory.available_to_sell = max(0, inventory.physical_stock - inventory.reserved_stock)

        self._log_movement(
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            movement_type=MovementType.DAMAGE,
            reference_number=reference_number,
            quantity_change=-quantity,
            quantity_before=inventory.physical_stock + quantity,
            quantity_after=inventory.physical_stock,
            user=user,
            reason=reason or 'Damaged stock'
        )

        self.db.commit()

        return {'success': True, 'damaged_quantity': quantity}

    def add_returned_stock(self, sku_code, warehouse_id, quantity, reference_number, user='system', reason=''):
        """Add returned stock back to inventory"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return {'success': False, 'error': f'SKU {sku_code} not found'}

        inventory = self.db.query(SKUInventory).filter_by(
            sku_id=sku.id, warehouse_id=warehouse_id
        ).first()

        if not inventory:
            return {'success': False, 'error': 'Inventory record not found'}

        quantity_before = inventory.physical_stock
        inventory.physical_stock += quantity
        inventory.returned_stock -= quantity
        inventory.available_to_sell = max(0, inventory.physical_stock - inventory.reserved_stock)
        inventory.inventory_value = inventory.physical_stock * (sku.unit_cost or 0)

        self._log_movement(
            sku_id=sku.id,
            warehouse_id=warehouse_id,
            movement_type=MovementType.RETURN,
            reference_number=reference_number,
            quantity_change=quantity,
            quantity_before=quantity_before,
            quantity_after=inventory.physical_stock,
            user=user,
            reason=reason or 'Returned stock added'
        )

        self.db.commit()

        return {'success': True, 'quantity_added': quantity}

    # =====================================================================
    # INVENTORY MOVEMENT LOGGING
    # =====================================================================

    def _log_movement(self, sku_id, warehouse_id, movement_type, reference_number,
                     quantity_change, quantity_before, quantity_after, user, reason=''):
        """Log every inventory movement (audit trail)"""
        movement = InventoryMovement(
            sku_id=sku_id,
            warehouse_id=warehouse_id,
            movement_type=movement_type,
            reference_number=reference_number,
            quantity_before=quantity_before,
            quantity_change=quantity_change,
            quantity_after=quantity_after,
            user=user,
            reason=reason
        )
        self.db.add(movement)
        self.db.commit()

    def get_movement_history(self, sku_code, warehouse_id=None, limit=100):
        """Get inventory movement history"""
        sku = self.db.query(SKUMaster).filter_by(sku=sku_code).first()
        if not sku:
            return []

        query = self.db.query(InventoryMovement).filter_by(sku_id=sku.id)
        if warehouse_id:
            query = query.filter_by(warehouse_id=warehouse_id)

        movements = query.order_by(InventoryMovement.created_at.desc()).limit(limit).all()
        return [m.to_dict() for m in movements]

    # =====================================================================
    # STOCK LEVEL CHECKS
    # =====================================================================

    def get_low_stock_skus(self, warehouse_id):
        """Get SKUs below reorder level"""
        inventories = self.db.query(SKUInventory).filter_by(warehouse_id=warehouse_id).all()
        low_stock = []

        for inv in inventories:
            sku = inv.sku_master
            if inv.physical_stock <= sku.reorder_level:
                low_stock.append({
                    'sku': sku.sku,
                    'product': sku.product_name,
                    'current_stock': inv.physical_stock,
                    'reorder_level': sku.reorder_level,
                    'shortage': max(0, sku.reorder_level - inv.physical_stock)
                })

        return low_stock

    def get_overstock_skus(self, warehouse_id):
        """Get SKUs above max stock level"""
        inventories = self.db.query(SKUInventory).filter_by(warehouse_id=warehouse_id).all()
        overstock = []

        for inv in inventories:
            sku = inv.sku_master
            if inv.physical_stock > sku.max_stock:
                overstock.append({
                    'sku': sku.sku,
                    'product': sku.product_name,
                    'current_stock': inv.physical_stock,
                    'max_stock': sku.max_stock,
                    'excess': inv.physical_stock - sku.max_stock
                })

        return overstock

    # =====================================================================
    # INVENTORY VALIDATION
    # =====================================================================

    def validate_inventory_integrity(self, warehouse_id):
        """Validate inventory data integrity"""
        issues = []
        inventories = self.db.query(SKUInventory).filter_by(warehouse_id=warehouse_id).all()

        for inv in inventories:
            # Check negative stock
            if inv.physical_stock < 0:
                issues.append({
                    'type': 'negative_stock',
                    'sku': inv.sku_master.sku,
                    'stock': inv.physical_stock
                })

            # Check reserved > physical
            if inv.reserved_stock > inv.physical_stock:
                issues.append({
                    'type': 'over_reservation',
                    'sku': inv.sku_master.sku,
                    'physical': inv.physical_stock,
                    'reserved': inv.reserved_stock
                })

            # Check available_to_sell calculation
            expected_ats = max(0, inv.physical_stock - inv.reserved_stock)
            if inv.available_to_sell != expected_ats:
                issues.append({
                    'type': 'ats_calculation_error',
                    'sku': inv.sku_master.sku,
                    'expected': expected_ats,
                    'actual': inv.available_to_sell
                })

        return issues if issues else {'status': 'valid', 'message': 'No integrity issues found'}
