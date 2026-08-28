#!/usr/bin/env python3
"""Marketplace Integration API Routes"""

from flask import Blueprint, request, jsonify
from .shopify_connector import ShopifyConnector
import json

integrations_bp = Blueprint('integrations', __name__)

# Store active connectors
active_connectors = {}

@integrations_bp.route('/shopify/connect', methods=['POST'])
def connect_shopify():
    """Connect to Shopify store"""
    data = request.get_json()
    shop_url = data.get('shop_url')
    access_token = data.get('access_token')
    webhook_secret = data.get('webhook_secret', '')

    try:
        connector = ShopifyConnector(shop_url, access_token, webhook_secret)
        result = connector.authenticate()

        if result['success']:
            active_connectors['shopify'] = connector
            return jsonify({'success': True, 'message': 'Connected to Shopify', 'shop': result.get('shop')}), 200
        else:
            return jsonify({'success': False, 'error': result.get('error')}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@integrations_bp.route('/shopify/status', methods=['GET'])
def shopify_status():
    """Get Shopify connector status"""
    if 'shopify' not in active_connectors:
        return jsonify({'status': 'Not Connected'}), 404

    connector = active_connectors['shopify']
    return jsonify(connector.get_status()), 200

@integrations_bp.route('/shopify/sync', methods=['POST'])
def sync_shopify():
    """Sync Shopify orders & inventory"""
    if 'shopify' not in active_connectors:
        return jsonify({'success': False, 'error': 'Shopify not connected'}), 400

    connector = active_connectors['shopify']
    result = connector.sync('full')

    return jsonify({
        'success': True,
        'orders_synced': result.get('orders_synced'),
        'inventory_synced': result.get('inventory_synced'),
        'returns_synced': result.get('returns_synced'),
        'errors': result.get('errors', [])
    }), 200

@integrations_bp.route('/shopify/orders', methods=['GET'])
def get_shopify_orders():
    """Get Shopify orders"""
    if 'shopify' not in active_connectors:
        return jsonify({'error': 'Shopify not connected'}), 400

    connector = active_connectors['shopify']
    status = request.args.get('status', 'any')
    limit = request.args.get('limit', 100, type=int)

    result = connector.get_orders({'status': status}, limit)
    return jsonify(result), 200 if result['success'] else 400

@integrations_bp.route('/shopify/webhook', methods=['POST'])
def shopify_webhook():
    """Handle Shopify webhooks"""
    if 'shopify' not in active_connectors:
        return jsonify({'error': 'Shopify not connected'}), 400

    connector = active_connectors['shopify']
    body = request.data.decode('utf-8')

    if not connector.validate_webhook_signature(request.headers, body):
        return jsonify({'error': 'Invalid signature'}), 401

    event_type = request.headers.get('X-Shopify-Topic', '')
    payload = json.loads(body)

    result = connector.process_webhook(event_type, payload)
    return jsonify({'processed': True, 'action': result.get('action')}), 200

@integrations_bp.route('/health', methods=['GET'])
def health():
    """Service health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'Marketplace Integrations',
        'connectors': list(active_connectors.keys())
    }), 200
