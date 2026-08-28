#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Processing Engine - Full Order Lifecycle Management
=========================================================
Handles order creation, status transitions, fulfillment workflow,
and integration with inventory system.
"""

from datetime import datetime
from sqlalchemy import desc
from .models import (
    Order, OrderItem, OrderHistory, OrderStatus, PaymentStatus,
    SKUMaster, Customer, InventoryReservation
)
from .inventory_engine import InventoryEngine


class OrderProcessingEngine:
    """
    Complete order processing workflow.
    Implements order lifecycle: New → Confirmed → Payment Verified → Reserved → Picking → Packing → Dispatch → Delivered
    """

    def __init__(self, db_session):
        self.db = db_session
        self.inventory = InventoryEngine(db_session)

    # =====================================================================
    # ORDER CREATION
    # =====================================================================

    def create_order(self, order_data, user='system'):
        """
        Create a new order.
        order_data = {
            'order_number': str,
            'marketplace': str,
            'marketplace_order_id': str,
            'customer_name': str,
            'customer_email': str,
            'customer_phone': str,
            'shipping_address': str,
            'billing_address': str,
            'warehouse_id': int,
            'items': [{'sku_code': str, 'quantity': int, 'unit_price': float}],
            'subtotal': float,
            'shipping_cost': float,
            'tax': float,
            'discount': float,
            'notes': str
        }
        """
        # Check duplicate
        existing = self.db.query(Order).filter_by(
            order_number=order_data['order_number']
        ).first()
        if existing:
            return {'success': False, 'error': f'Order {order_data["order_number"]} already exists'}

        # Create order
        total = order_data.get('subtotal', 0) + order_data.get('shipping_cost', 0) + \
                order_data.get('tax', 0) - order_data.get('discount', 0)

        order = Order(
            order_number=order_data['order_number'],
            marketplace=order_data.get('marketplace', 'Direct'),
            marketplace_order_id=order_data.get('marketplace_order_id'),
            customer_name=order_data['customer_name'],
            customer_email=order_data.get('customer_email'),
            customer_phone=order_data.get('customer_phone'),
            shipping_address=order_data.get('shipping_address'),
            billing_address=order_data.get('billing_address'),
            warehouse_id=order_data['warehouse_id'],
            subtotal=order_data.get('subtotal', 0),
            shipping_cost=order_data.get('shipping_cost', 0),
            tax=order_data.get('tax', 0),
            discount=order_data.get('discount', 0),
            total=total,
            notes=order_data.get('notes', ''),
            order_status=OrderStatus.NEW,
            payment_status=PaymentStatus.PENDING
        )

        self.db.add(order)
        self.db.flush()

        # Add order items
        for item in order_data.get('items', []):
            order_item = OrderItem(
                order_id=order.id,
                sku_code=item['sku_code'],
                quantity_ordered=item['quantity'],
                unit_price=item.get('unit_price', 0),
                line_total=item['quantity'] * item.get('unit_price', 0)
            )
            self.db.add(order_item)

        self.db.commit()

        # Log history
        self._log_status_change(order.id, None, OrderStatus.NEW.value, user, 'Order created')

        return {'success': True, 'order_id': order.id, 'order_number': order.order_number}

    # =====================================================================
    # ORDER STATUS TRANSITIONS
    # =====================================================================

    def confirm_order(self, order_id, user='system'):
        """Confirm order (status: New → Confirmed)"""
        return self._change_status(order_id, OrderStatus.CONFIRMED, user, 'Order confirmed')

    def verify_payment(self, order_id, user='system'):
        """Verify payment (payment_status: Pending → Paid, order_status → Payment Verified)"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        order.payment_status = PaymentStatus.PAID
        return self._change_status(order_id, OrderStatus.PAYMENT_VERIFIED, user, 'Payment verified')

    def reserve_inventory(self, order_id, user='system'):
        """Reserve inventory for order (order_status → Inventory Reserved)"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        # Check inventory for all items
        availability = self.inventory.check_multi_sku_availability(
            [{'sku_code': item.sku_code, 'quantity': item.quantity_ordered} for item in order.items],
            order.warehouse_id
        )

        for check in availability:
            if not check['can_fulfill']:
                return {'success': False, 'error': f'Insufficient stock for {check["sku_code"]}'}

        # Reserve all items
        for item in order.items:
            result = self.inventory.reserve_inventory(
                order_id=order.id,
                order_item_id=item.id,
                sku_code=item.sku_code,
                quantity=item.quantity_ordered,
                warehouse_id=order.warehouse_id,
                user=user
            )
            if not result['success']:
                return result

        return self._change_status(order_id, OrderStatus.INVENTORY_RESERVED, user, 'Inventory reserved')

    def start_picking(self, order_id, user='system'):
        """Start picking items (order_status → Picking)"""
        return self._change_status(order_id, OrderStatus.PICKING, user, 'Started picking')

    def complete_picking(self, order_id, user='system'):
        """Complete picking (order_status → Picked)"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        # Mark items as picked
        for item in order.items:
            item.quantity_picked = item.quantity_ordered

        return self._change_status(order_id, OrderStatus.PICKED, user, 'Picking completed')

    def start_packing(self, order_id, user='system'):
        """Start packing items (order_status → Packing)"""
        return self._change_status(order_id, OrderStatus.PACKING, user, 'Started packing')

    def complete_packing(self, order_id, user='system'):
        """Complete packing (order_status → Packed)"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        # Mark items as packed
        for item in order.items:
            item.quantity_packed = item.quantity_ordered

        return self._change_status(order_id, OrderStatus.PACKED, user, 'Packing completed')

    def ready_for_dispatch(self, order_id, user='system'):
        """Mark ready for dispatch (order_status → Ready for Dispatch)"""
        return self._change_status(order_id, OrderStatus.READY_FOR_DISPATCH, user, 'Ready for dispatch')

    def dispatch_order(self, order_id, tracking_number=None, user='system'):
        """Dispatch order and deduct from inventory"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        # Deduct inventory
        for item in order.items:
            result = self.inventory.deduct_stock(
                sku_code=item.sku_code,
                warehouse_id=order.warehouse_id,
                quantity=item.quantity_ordered,
                movement_type='Sales Order',
                reference_number=order.order_number,
                user=user,
                reason=f'Order {order.order_number} dispatched'
            )
            if not result['success']:
                return result
            item.quantity_shipped = item.quantity_ordered

        order.tracking_number = tracking_number
        order.shipped_date = datetime.utcnow()

        return self._change_status(order_id, OrderStatus.DISPATCHED, user, f'Order dispatched. Tracking: {tracking_number}')

    def mark_delivered(self, order_id, delivery_date=None, user='system'):
        """Mark order as delivered"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        order.delivered_date = delivery_date or datetime.utcnow()
        return self._change_status(order_id, OrderStatus.DELIVERED, user, 'Order delivered')

    def cancel_order(self, order_id, reason='', user='system'):
        """Cancel order and release reservations"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        # Release all reservations
        reservations = self.db.query(InventoryReservation).filter_by(
            order_id=order_id, is_active=True
        ).all()

        for reservation in reservations:
            self.inventory.release_reservation(reservation.id, user)

        return self._change_status(order_id, OrderStatus.CANCELLED, user, f'Order cancelled. {reason}')

    def hold_order(self, order_id, reason='', user='system'):
        """Put order on hold"""
        return self._change_status(order_id, OrderStatus.ON_HOLD, user, f'Order on hold. {reason}')

    def _change_status(self, order_id, new_status, user, reason):
        """Internal method to change order status"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        old_status = order.order_status
        order.order_status = new_status
        order.updated_at = datetime.utcnow()

        self._log_status_change(order_id, old_status.value if old_status else None, new_status.value, user, reason)

        self.db.commit()
        return {'success': True, 'order_id': order_id, 'new_status': new_status.value}

    # =====================================================================
    # RETURNS & REFUNDS
    # =====================================================================

    def process_return(self, order_id, returned_items, refund_reason, user='system'):
        """
        Process order return.
        returned_items = [{'sku_code': str, 'quantity': int, 'condition': 'sellable|damaged'}]
        """
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return {'success': False, 'error': 'Order not found'}

        # Process each returned item
        for item_data in returned_items:
            sku_code = item_data['sku_code']
            quantity = item_data['quantity']
            condition = item_data.get('condition', 'sellable')

            if condition == 'sellable':
                # Add back to available inventory
                self.inventory.add_returned_stock(
                    sku_code=sku_code,
                    warehouse_id=order.warehouse_id,
                    quantity=quantity,
                    reference_number=order.order_number,
                    user=user,
                    reason=refund_reason
                )
            elif condition == 'damaged':
                # Mark as damaged
                self.inventory.mark_damaged(
                    sku_code=sku_code,
                    warehouse_id=order.warehouse_id,
                    quantity=quantity,
                    reference_number=order.order_number,
                    user=user,
                    reason=refund_reason
                )

        # Update order status
        if order.order_status == OrderStatus.DELIVERED:
            order.order_status = OrderStatus.RETURNED
        else:
            order.order_status = OrderStatus.PARTIALLY_RETURNED

        order.payment_status = PaymentStatus.REFUNDED
        self._log_status_change(order_id, OrderStatus.DELIVERED.value, OrderStatus.RETURNED.value, user, refund_reason)

        self.db.commit()
        return {'success': True, 'order_id': order_id, 'status': 'Returned'}

    # =====================================================================
    # ORDER SEARCH & RETRIEVAL
    # =====================================================================

    def get_order(self, order_id):
        """Get order details"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        return order.to_dict() if order else None

    def search_orders(self, filters=None, limit=100):
        """
        Search orders with filters.
        filters = {
            'order_number': str,
            'marketplace': str,
            'order_status': str,
            'payment_status': str,
            'customer_name': str,
            'warehouse_id': int,
            'date_from': datetime,
            'date_to': datetime
        }
        """
        query = self.db.query(Order)

        if not filters:
            filters = {}

        if filters.get('order_number'):
            query = query.filter(Order.order_number.ilike(f"%{filters['order_number']}%"))

        if filters.get('marketplace'):
            query = query.filter_by(marketplace=filters['marketplace'])

        if filters.get('order_status'):
            query = query.filter_by(order_status=filters['order_status'])

        if filters.get('customer_name'):
            query = query.filter(Order.customer_name.ilike(f"%{filters['customer_name']}%"))

        if filters.get('warehouse_id'):
            query = query.filter_by(warehouse_id=filters['warehouse_id'])

        if filters.get('date_from'):
            query = query.filter(Order.created_at >= filters['date_from'])

        if filters.get('date_to'):
            query = query.filter(Order.created_at <= filters['date_to'])

        orders = query.order_by(desc(Order.created_at)).limit(limit).all()
        return [o.to_dict() for o in orders]

    def get_order_history(self, order_id):
        """Get order status history"""
        history = self.db.query(OrderHistory).filter_by(order_id=order_id).order_by(
            desc(OrderHistory.created_at)
        ).all()

        return [{
            'timestamp': h.created_at.isoformat() if h.created_at else None,
            'old_status': h.old_status,
            'new_status': h.new_status,
            'changed_by': h.changed_by,
            'reason': h.change_reason
        } for h in history]

    # =====================================================================
    # ORDER ANALYTICS
    # =====================================================================

    def get_dashboard_stats(self):
        """Get order dashboard statistics"""
        total_orders = self.db.query(Order).count()
        pending_orders = self.db.query(Order).filter(
            Order.order_status.in_([OrderStatus.NEW, OrderStatus.CONFIRMED])
        ).count()
        picking_orders = self.db.query(Order).filter_by(order_status=OrderStatus.PICKING).count()
        packing_orders = self.db.query(Order).filter_by(order_status=OrderStatus.PACKING).count()
        ready_dispatch = self.db.query(Order).filter_by(
            order_status=OrderStatus.READY_FOR_DISPATCH
        ).count()
        dispatched = self.db.query(Order).filter_by(order_status=OrderStatus.DISPATCHED).count()
        delivered = self.db.query(Order).filter_by(order_status=OrderStatus.DELIVERED).count()
        cancelled = self.db.query(Order).filter_by(order_status=OrderStatus.CANCELLED).count()
        returned = self.db.query(Order).filter(
            Order.order_status.in_([OrderStatus.RETURNED, OrderStatus.PARTIALLY_RETURNED])
        ).count()

        return {
            'total_orders': total_orders,
            'pending': pending_orders,
            'picking': picking_orders,
            'packing': packing_orders,
            'ready_dispatch': ready_dispatch,
            'dispatched': dispatched,
            'delivered': delivered,
            'cancelled': cancelled,
            'returned': returned
        }

    def get_marketplace_stats(self):
        """Get orders by marketplace"""
        results = self.db.query(Order.marketplace, func.count(Order.id)).group_by(
            Order.marketplace
        ).all()
        return {marketplace: count for marketplace, count in results}

    # =====================================================================
    # INTERNAL HELPERS
    # =====================================================================

    def _log_status_change(self, order_id, old_status, new_status, user, reason):
        """Log order status change to history"""
        history = OrderHistory(
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            changed_by=user,
            change_reason=reason
        )
        self.db.add(history)
        self.db.commit()


# Import func for aggregation
from sqlalchemy import func
