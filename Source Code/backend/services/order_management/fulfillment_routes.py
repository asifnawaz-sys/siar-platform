#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fulfillment API Routes
======================
REST API endpoints for picking, packing, and shipment management.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from .fulfillment_engine import FulfillmentEngine, PickingList, PackingList, Shipment
from .models import Order

fulfillment_bp = Blueprint('fulfillment', __name__)

# Database setup
DB_PATH = os.path.join(os.path.dirname(__file__), '../../../Data/database/orders.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# =====================================================================
# PICKING LIST ENDPOINTS
# =====================================================================

@fulfillment_bp.route('/picking-lists', methods=['POST'])
def create_picking_list():
    """Create picking list from orders"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.create_picking_list(
        warehouse_id=data['warehouse_id'],
        orders=data['order_ids'],
        user=data.get('user', 'system')
    )
    session.close()

    status = 201 if result['success'] else 400
    return jsonify(result), status

@fulfillment_bp.route('/picking-lists/<int:picking_list_id>/assign', methods=['POST'])
def assign_picking_list(picking_list_id):
    """Assign picking list to staff"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.assign_picking_list(
        picking_list_id=picking_list_id,
        assigned_to=data['assigned_to'],
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/picking-lists/<int:picking_list_id>/start', methods=['POST'])
def start_picking(picking_list_id):
    """Start picking operation"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.start_picking(
        picking_list_id=picking_list_id,
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/picking-lists/<int:picking_list_id>/items/<int:item_id>/pick', methods=['POST'])
def record_picked_item(picking_list_id, item_id):
    """Record item picked"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.record_picked_item(
        picking_list_id=picking_list_id,
        picking_item_id=item_id,
        quantity_picked=data['quantity_picked'],
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/picking-lists/<int:picking_list_id>/complete', methods=['POST'])
def complete_picking(picking_list_id):
    """Complete picking list"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.complete_picking(
        picking_list_id=picking_list_id,
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/picking-lists/<int:picking_list_id>', methods=['GET'])
def get_picking_list(picking_list_id):
    """Get picking list details"""
    session = get_session()
    picking_list = session.query(PickingList).filter_by(id=picking_list_id).first()
    session.close()

    if not picking_list:
        return jsonify({'error': 'Picking list not found'}), 404

    return jsonify({
        'id': picking_list.id,
        'picking_number': picking_list.picking_number,
        'status': picking_list.status.value if picking_list.status else None,
        'warehouse_id': picking_list.warehouse_id,
        'assigned_to': picking_list.assigned_to,
        'order_count': picking_list.order_count,
        'item_count': picking_list.item_count,
        'picked_count': picking_list.picked_count,
        'created_at': picking_list.created_at.isoformat() if picking_list.created_at else None,
        'completed_at': picking_list.completed_at.isoformat() if picking_list.completed_at else None
    }), 200

# =====================================================================
# PACKING LIST ENDPOINTS
# =====================================================================

@fulfillment_bp.route('/packing-lists', methods=['POST'])
def create_packing_list():
    """Create packing list from picking list"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.create_packing_list(
        picking_list_id=data['picking_list_id'],
        warehouse_id=data['warehouse_id'],
        user=data.get('user', 'system')
    )
    session.close()

    status = 201 if result['success'] else 400
    return jsonify(result), status

@fulfillment_bp.route('/packing-lists/<int:packing_list_id>/start', methods=['POST'])
def start_packing(packing_list_id):
    """Start packing operation"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.start_packing(
        packing_list_id=packing_list_id,
        assigned_to=data['assigned_to'],
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/packing-lists/<int:packing_list_id>/items/<int:item_id>/pack', methods=['POST'])
def record_packed_item(packing_list_id, item_id):
    """Record item packed"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.record_packed_item(
        packing_list_id=packing_list_id,
        packing_item_id=item_id,
        quantity_packed=data['quantity_packed'],
        box_number=data['box_number'],
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/packing-lists/<int:packing_list_id>/boxes', methods=['POST'])
def create_packed_box(packing_list_id):
    """Record packed box"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.create_packed_box(
        packing_list_id=packing_list_id,
        box_number=data['box_number'],
        length=data['length'],
        width=data['width'],
        height=data['height'],
        weight=data['weight'],
        contents=data.get('contents', [])
    )
    session.close()

    status = 201 if result['success'] else 400
    return jsonify(result), status

@fulfillment_bp.route('/packing-lists/<int:packing_list_id>/complete', methods=['POST'])
def complete_packing(packing_list_id):
    """Complete packing (ready for QC)"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.complete_packing(
        packing_list_id=packing_list_id,
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/packing-lists/<int:packing_list_id>/qc', methods=['POST'])
def quality_check(packing_list_id):
    """Perform quality check"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.perform_quality_check(
        packing_list_id=packing_list_id,
        qc_passed=data['qc_passed'],
        qc_notes=data.get('qc_notes', ''),
        qc_by=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/packing-lists/<int:packing_list_id>', methods=['GET'])
def get_packing_list(packing_list_id):
    """Get packing list details"""
    session = get_session()
    packing_list = session.query(PackingList).filter_by(id=packing_list_id).first()
    session.close()

    if not packing_list:
        return jsonify({'error': 'Packing list not found'}), 404

    return jsonify({
        'id': packing_list.id,
        'packing_number': packing_list.packing_number,
        'status': packing_list.status.value if packing_list.status else None,
        'qc_status': packing_list.qc_status,
        'warehouse_id': packing_list.warehouse_id,
        'assigned_to': packing_list.assigned_to,
        'order_count': packing_list.order_count,
        'item_count': packing_list.item_count,
        'box_count': packing_list.box_count,
        'total_weight': packing_list.total_weight,
        'total_volume': packing_list.total_volume,
        'created_at': packing_list.created_at.isoformat() if packing_list.created_at else None,
        'completed_at': packing_list.completed_at.isoformat() if packing_list.completed_at else None
    }), 200

# =====================================================================
# SHIPMENT ENDPOINTS
# =====================================================================

@fulfillment_bp.route('/shipments', methods=['POST'])
def create_shipment():
    """Create shipment"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.create_shipment(
        order_id=data['order_id'],
        carrier=data['carrier'],
        weight=data['weight'],
        dimensions=data.get('dimensions', {}),
        shipping_cost=data.get('shipping_cost', 0.0),
        user=data.get('user', 'system')
    )
    session.close()

    status = 201 if result['success'] else 400
    return jsonify(result), status

@fulfillment_bp.route('/shipments/<int:shipment_id>/tracking', methods=['POST'])
def assign_tracking(shipment_id):
    """Assign tracking number to shipment"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.assign_tracking_number(
        shipment_id=shipment_id,
        tracking_number=data['tracking_number'],
        label_url=data.get('label_url', ''),
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/shipments/<int:shipment_id>/pickup', methods=['POST'])
def mark_pickup(shipment_id):
    """Mark shipment as picked up"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.mark_picked_up(
        shipment_id=shipment_id,
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/shipments/<int:shipment_id>/status', methods=['POST'])
def update_shipment_status(shipment_id):
    """Update shipment tracking status"""
    data = request.get_json()
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    result = fulfillment.update_shipment_status(
        shipment_id=shipment_id,
        new_status=data['status'],
        status_detail=data.get('detail', ''),
        location=data.get('location', ''),
        user=data.get('user', 'system')
    )
    session.close()

    return jsonify(result), 200 if result['success'] else 400

@fulfillment_bp.route('/shipments/<int:shipment_id>/tracking', methods=['GET'])
def get_tracking(shipment_id):
    """Get shipment tracking information"""
    session = get_session()
    fulfillment = FulfillmentEngine(session)

    tracking = fulfillment.get_shipment_tracking(shipment_id)
    session.close()

    if not tracking:
        return jsonify({'error': 'Shipment not found'}), 404

    return jsonify(tracking), 200

@fulfillment_bp.route('/shipments/<int:shipment_id>', methods=['GET'])
def get_shipment(shipment_id):
    """Get shipment details"""
    session = get_session()
    shipment = session.query(Shipment).filter_by(id=shipment_id).first()
    session.close()

    if not shipment:
        return jsonify({'error': 'Shipment not found'}), 404

    return jsonify({
        'id': shipment.id,
        'shipment_number': shipment.shipment_number,
        'order_id': shipment.order_id,
        'status': shipment.status.value if shipment.status else None,
        'carrier': shipment.carrier.value if shipment.carrier else None,
        'tracking_number': shipment.tracking_number,
        'weight': shipment.weight,
        'shipping_cost': shipment.shipping_cost,
        'estimated_delivery': shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
        'delivered_at': shipment.delivered_at.isoformat() if shipment.delivered_at else None,
        'created_at': shipment.created_at.isoformat() if shipment.created_at else None
    }), 200

# =====================================================================
# DASHBOARD ENDPOINTS
# =====================================================================

@fulfillment_bp.route('/dashboard/stats', methods=['GET'])
def fulfillment_dashboard_stats():
    """Get fulfillment dashboard statistics"""
    session = get_session()

    picking_lists = session.query(PickingList).count()
    picking_in_progress = session.query(PickingList).filter_by(
        status='In Progress'
    ).count()

    packing_lists = session.query(PackingList).count()
    packing_in_progress = session.query(PackingList).filter_by(
        status='In Progress'
    ).count()

    shipments = session.query(Shipment).count()
    shipments_delivered = session.query(Shipment).filter_by(
        status='Delivered'
    ).count()

    session.close()

    return jsonify({
        'picking_lists_total': picking_lists,
        'picking_in_progress': picking_in_progress,
        'packing_lists_total': packing_lists,
        'packing_in_progress': packing_in_progress,
        'shipments_total': shipments,
        'shipments_delivered': shipments_delivered,
        'timestamp': datetime.utcnow().isoformat()
    }), 200

# =====================================================================
# HEALTH CHECK
# =====================================================================

@fulfillment_bp.route('/health', methods=['GET'])
def fulfillment_health():
    """Service health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'Fulfillment System',
        'version': '1.0',
        'features': [
            'picking_management',
            'packing_management',
            'shipment_tracking',
            'quality_control'
        ]
    }), 200
