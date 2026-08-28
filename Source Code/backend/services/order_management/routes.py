#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Management & Inventory API Routes
========================================
30+ REST API endpoints for complete order and inventory management
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from .models import (
    Base, Warehouse, SKUMaster, SKUInventory, Order, OrderItem,
    Customer, InventoryMovement, OrderStatus, PaymentStatus
)
from .inventory_engine import InventoryEngine
from .order_engine import OrderProcessingEngine
from .order_reporting import OrderReportingEngine

order_bp = Blueprint('order_management', __name__)

# Database setup
DB_PATH = os.path.join(os.path.dirname(__file__), '../../../Data/database/orders.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# =====================================================================
# WAREHOUSE ENDPOINTS
# =====================================================================

@order_bp.route('/warehouses', methods=['GET'])
def list_warehouses():
    """Get all warehouses"""
    session = get_session()
    warehouses = session.query(Warehouse).filter_by(is_active=True).all()
    session.close()
    return jsonify([w.to_dict() for w in warehouses]), 200

@order_bp.route('/warehouses', methods=['POST'])
def create_warehouse():
    """Create new warehouse"""
    data = request.get_json()
    session = get_session()

    warehouse = Warehouse(
        code=data['code'],
        name=data['name'],
        location=data.get('location'),
        address=data.get('address'),
        contact=data.get('contact')
    )
    session.add(warehouse)
    session.commit()
    result = warehouse.to_dict()
    session.close()

    return jsonify({'success': True, 'warehouse': result}), 201

@order_bp.route('/warehouses/<int:warehouse_id>', methods=['GET'])
def get_warehouse(warehouse_id):
    """Get warehouse details"""
    session = get_session()
    warehouse = session.query(Warehouse).filter_by(id=warehouse_id).first()
    session.close()

    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404
    return jsonify(warehouse.to_dict()), 200

# =====================================================================
# SKU MASTER ENDPOINTS
# =====================================================================

@order_bp.route('/skus', methods=['GET'])
def list_skus():
    """Get all active SKUs"""
    session = get_session()
    skus = session.query(SKUMaster).filter_by(is_active=True).limit(500).all()
    session.close()
    return jsonify([s.to_dict() for s in skus]), 200

@order_bp.route('/skus', methods=['POST'])
def create_sku():
    """Create new SKU"""
    data = request.get_json()
    session = get_session()

    sku = SKUMaster(
        sku=data['sku'],
        product_name=data['product_name'],
        variant=data.get('variant'),
        size=data.get('size'),
        color=data.get('color'),
        brand=data.get('brand'),
        category=data.get('category'),
        unit_cost=data.get('unit_cost', 0),
        retail_price=data.get('retail_price', 0),
        barcode=data.get('barcode'),
        reorder_level=data.get('reorder_level', 10),
        max_stock=data.get('max_stock', 1000)
    )
    session.add(sku)
    session.commit()
    result = sku.to_dict()
    session.close()

    return jsonify({'success': True, 'sku': result}), 201

@order_bp.route('/skus/<sku_code>', methods=['GET'])
def get_sku(sku_code):
    """Get SKU details"""
    session = get_session()
    sku = session.query(SKUMaster).filter_by(sku=sku_code).first()

    if not sku:
        session.close()
        return jsonify({'error': 'SKU not found'}), 404

    result = sku.to_dict()
    session.close()
    return jsonify(result), 200

@order_bp.route('/skus/search', methods=['POST'])
def search_skus():
    """Search SKUs by name, code, barcode"""
    data = request.get_json()
    search_term = data.get('q', '').lower()
    session = get_session()

    skus = session.query(SKUMaster).filter(
        (SKUMaster.sku.ilike(f"%{search_term}%")) |
        (SKUMaster.product_name.ilike(f"%{search_term}%")) |
        (SKUMaster.barcode.ilike(f"%{search_term}%"))
    ).limit(50).all()

    session.close()
    return jsonify([s.to_dict() for s in skus]), 200

# =====================================================================
# INVENTORY ENDPOINTS
# =====================================================================

@order_bp.route('/inventory/<sku_code>', methods=['GET'])
def get_sku_inventory(sku_code):
    """Get inventory for SKU across all warehouses"""
    session = get_session()
    inventory_engine = InventoryEngine(session)

    result = inventory_engine.get_sku_total_inventory(sku_code)
    session.close()

    if not result['sku']:
        return jsonify({'error': 'SKU not found'}), 404
    return jsonify(result), 200

@order_bp.route('/inventory/<sku_code>/<int:warehouse_id>', methods=['GET'])
def get_warehouse_sku_inventory(sku_code, warehouse_id):
    """Get SKU inventory for specific warehouse"""
    session = get_session()
    inventory_engine = InventoryEngine(session)

    inventory = inventory_engine.get_sku_inventory(sku_code, warehouse_id)
    session.close()

    if not inventory:
        return jsonify({'error': 'Inventory not found'}), 404
    return jsonify(inventory.to_dict()), 200

@order_bp.route('/inventory/adjust', methods=['POST'])
def adjust_inventory():
    """Manually adjust inventory"""
    data = request.get_json()
    session = get_session()
    inventory_engine = InventoryEngine(session)

    if data['action'] == 'add':
        result = inventory_engine.add_stock(
            sku_code=data['sku_code'],
            warehouse_id=data['warehouse_id'],
            quantity=data['quantity'],
            movement_type='Manual Adjustment',
            reference_number=data.get('reference', 'ADJ'),
            user=data.get('user', 'system'),
            reason=data.get('reason', 'Manual adjustment')
        )
    elif data['action'] == 'deduct':
        result = inventory_engine.deduct_stock(
            sku_code=data['sku_code'],
            warehouse_id=data['warehouse_id'],
            quantity=data['quantity'],
            movement_type='Manual Adjustment',
            reference_number=data.get('reference', 'ADJ'),
            user=data.get('user', 'system'),
            reason=data.get('reason', 'Manual adjustment')
        )

    session.close()
    return jsonify(result), 200 if result['success'] else 400

@order_bp.route('/inventory/low-stock/<int:warehouse_id>', methods=['GET'])
def get_low_stock(warehouse_id):
    """Get SKUs below reorder level"""
    session = get_session()
    inventory_engine = InventoryEngine(session)

    low_stock = inventory_engine.get_low_stock_skus(warehouse_id)
    session.close()

    return jsonify(low_stock), 200

@order_bp.route('/inventory/movement-history/<sku_code>', methods=['GET'])
def get_inventory_history(sku_code):
    """Get inventory movement history"""
    warehouse_id = request.args.get('warehouse_id', type=int)
    limit = request.args.get('limit', 100, type=int)

    session = get_session()
    inventory_engine = InventoryEngine(session)

    history = inventory_engine.get_movement_history(sku_code, warehouse_id, limit)
    session.close()

    return jsonify(history), 200

@order_bp.route('/inventory/validate/<int:warehouse_id>', methods=['GET'])
def validate_inventory(warehouse_id):
    """Validate inventory integrity"""
    session = get_session()
    inventory_engine = InventoryEngine(session)

    issues = inventory_engine.validate_inventory_integrity(warehouse_id)
    session.close()

    return jsonify(issues), 200

# =====================================================================
# ORDER ENDPOINTS
# =====================================================================

@order_bp.route('/orders', methods=['POST'])
def create_order():
    """Create new order"""
    data = request.get_json()
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    result = order_engine.create_order(data, user=data.get('user', 'system'))
    session.close()

    status = 201 if result['success'] else 400
    return jsonify(result), status

@order_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order(order_id):
    """Get order details"""
    session = get_session()
    order = session.query(Order).filter_by(id=order_id).first()
    session.close()

    if not order:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify(order.to_dict()), 200

@order_bp.route('/orders/search', methods=['POST'])
def search_orders():
    """Search orders with filters"""
    filters = request.get_json() or {}
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    results = order_engine.search_orders(filters)
    session.close()

    return jsonify(results), 200

@order_bp.route('/orders/<int:order_id>/status', methods=['POST'])
def update_order_status(order_id):
    """Update order status"""
    data = request.get_json()
    action = data['action']
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    actions = {
        'confirm': order_engine.confirm_order,
        'verify_payment': order_engine.verify_payment,
        'reserve_inventory': order_engine.reserve_inventory,
        'start_picking': order_engine.start_picking,
        'complete_picking': order_engine.complete_picking,
        'start_packing': order_engine.start_packing,
        'complete_packing': order_engine.complete_packing,
        'ready_dispatch': order_engine.ready_for_dispatch,
        'dispatch': order_engine.dispatch_order,
        'deliver': order_engine.mark_delivered,
        'cancel': order_engine.cancel_order,
        'hold': order_engine.hold_order
    }

    if action not in actions:
        session.close()
        return jsonify({'error': 'Invalid action'}), 400

    if action == 'dispatch':
        result = actions[action](order_id, data.get('tracking_number'), data.get('user', 'system'))
    elif action in ['cancel', 'hold']:
        result = actions[action](order_id, data.get('reason', ''), data.get('user', 'system'))
    else:
        result = actions[action](order_id, data.get('user', 'system'))

    session.close()
    return jsonify(result), 200 if result['success'] else 400

@order_bp.route('/orders/<int:order_id>/return', methods=['POST'])
def return_order(order_id):
    """Process order return"""
    data = request.get_json()
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    result = order_engine.process_return(
        order_id,
        data.get('items', []),
        data.get('reason', 'Customer return'),
        data.get('user', 'system')
    )

    session.close()
    return jsonify(result), 200 if result['success'] else 400

@order_bp.route('/orders/<int:order_id>/history', methods=['GET'])
def get_order_history(order_id):
    """Get order status history"""
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    history = order_engine.get_order_history(order_id)
    session.close()

    return jsonify(history), 200

# =====================================================================
# DASHBOARD & REPORTING
# =====================================================================

@order_bp.route('/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Get order dashboard statistics"""
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    stats = order_engine.get_dashboard_stats()
    session.close()

    return jsonify(stats), 200

@order_bp.route('/dashboard/marketplace-stats', methods=['GET'])
def get_marketplace_stats():
    """Get orders by marketplace"""
    session = get_session()
    order_engine = OrderProcessingEngine(session)

    stats = order_engine.get_marketplace_stats()
    session.close()

    return jsonify(stats), 200

# =====================================================================
# ORDER LIFECYCLE & STATUS TRACKING
# =====================================================================

@order_bp.route('/reporting/status-counts', methods=['GET'])
def get_status_counts():
    """Get order count by status"""
    session = get_session()
    reporting = OrderReportingEngine(session)

    status_counts = reporting.get_status_wise_orders()
    session.close()

    return jsonify(status_counts), 200

@order_bp.route('/reporting/orders-by-status/<status>', methods=['GET'])
def get_orders_by_status(status):
    """Get all orders with specific status"""
    limit = request.args.get('limit', 100, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    orders = reporting.get_orders_by_status(status, limit)
    session.close()

    if isinstance(orders, dict) and 'error' in orders:
        return jsonify(orders), 400
    return jsonify(orders), 200

@order_bp.route('/reporting/order-lifecycle/<int:order_id>', methods=['GET'])
def get_order_lifecycle(order_id):
    """Get complete order lifecycle timeline"""
    session = get_session()
    reporting = OrderReportingEngine(session)

    lifecycle = reporting.get_order_lifecycle(order_id)
    session.close()

    if not lifecycle:
        return jsonify({'error': 'Order not found'}), 404
    return jsonify(lifecycle), 200

@order_bp.route('/reporting/cycle-metrics', methods=['GET'])
def get_cycle_metrics():
    """Get order cycle metrics for last N days"""
    days = request.args.get('days', 30, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    metrics = reporting.get_order_cycle_metrics(days)
    session.close()

    return jsonify(metrics), 200

@order_bp.route('/reporting/turnaround-times', methods=['GET'])
def get_turnaround_times():
    """Get average time in each order status"""
    session = get_session()
    reporting = OrderReportingEngine(session)

    avg_times = reporting.get_average_turnaround_times()
    session.close()

    return jsonify(avg_times), 200

@order_bp.route('/reporting/marketplace-breakdown', methods=['GET'])
def get_marketplace_breakdown():
    """Get order statistics by marketplace"""
    days = request.args.get('days', 30, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    stats = reporting.get_marketplace_stats(days)
    session.close()

    return jsonify(stats), 200

@order_bp.route('/reporting/daily-trends', methods=['GET'])
def get_daily_trends():
    """Get daily order creation/fulfillment trends"""
    days = request.args.get('days', 30, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    trends = reporting.get_daily_order_trends(days)
    session.close()

    return jsonify(trends), 200

@order_bp.route('/reporting/status-transitions', methods=['GET'])
def get_status_transitions():
    """Get status transition matrix"""
    days = request.args.get('days', 30, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    transitions = reporting.get_status_transition_matrix(days)
    session.close()

    return jsonify(transitions), 200

@order_bp.route('/reporting/slow-orders', methods=['GET'])
def get_slow_orders():
    """Get orders taking longer than threshold"""
    threshold_hours = request.args.get('threshold_hours', 48, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    slow_orders = reporting.get_slow_orders(threshold_hours)
    session.close()

    return jsonify(slow_orders), 200

@order_bp.route('/reporting/full-dashboard', methods=['GET'])
def get_full_dashboard():
    """Get complete order dashboard with all metrics"""
    days = request.args.get('days', 30, type=int)
    session = get_session()
    reporting = OrderReportingEngine(session)

    dashboard = reporting.get_full_dashboard(days)
    session.close()

    return jsonify(dashboard), 200

# =====================================================================
# HEALTH CHECK
# =====================================================================

@order_bp.route('/health', methods=['GET'])
def health():
    """Service health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'Order Management & Inventory',
        'version': '1.0',
        'features': [
            'order_processing',
            'inventory_management',
            'warehouse_management',
            'sku_tracking'
        ]
    }), 200

@order_bp.route('/stats', methods=['GET'])
def service_stats():
    """Service statistics"""
    session = get_session()

    total_orders = session.query(Order).count()
    total_skus = session.query(SKUMaster).count()
    total_warehouses = session.query(Warehouse).count()

    session.close()

    return jsonify({
        'total_orders': total_orders,
        'total_skus': total_skus,
        'total_warehouses': total_warehouses,
        'timestamp': datetime.utcnow().isoformat()
    }), 200
