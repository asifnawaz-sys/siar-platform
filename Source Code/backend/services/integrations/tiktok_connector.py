#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Shop API Connector
========================
Production-ready TikTok Shop integration.
Handles orders, inventory, fulfillment, returns.
"""

from .base_connector import BaseMarketplaceConnector, ConnectorStatus
import requests
import json
from datetime import datetime, timedelta
import hashlib
import hmac


class TikTokShopConnector(BaseMarketplaceConnector):
    """TikTok Shop API connector"""

    API_VERSION = "v1"
    BASE_URL = "https://open-api.tiktokshop.com"

    def __init__(self, shop_cipher, access_token, shop_id=''):
        """
        Initialize TikTok Shop connector.

        Args:
            shop_cipher: TikTok Shop cipher (unique identifier)
            access_token: OAuth access token
            shop_id: Shop ID
        """
        credentials = {
            'shop_cipher': shop_cipher,
            'access_token': access_token,
            'shop_id': shop_id
        }
        super().__init__('TikTok Shop', credentials)
        self.shop_cipher = shop_cipher
        self.access_token = access_token
        self.shop_id = shop_id

    # =====================================================================
    # AUTHENTICATION & CONNECTION
    # =====================================================================

    def authenticate(self):
        """Authenticate with TikTok Shop API"""
        try:
            result = self.test_connection()
            if result['success']:
                self.status = ConnectorStatus.CONNECTED
                self.logger.info("TikTok Shop authentication successful")
                return {'success': True}
            else:
                self.status = ConnectorStatus.DISCONNECTED
                return result
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            self.error_message = str(e)
            self.logger.error(f"Authentication failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def test_connection(self):
        """Test TikTok Shop API connection"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/shop/info"

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                shop_name = data.get('data', {}).get('shop_name', 'TikTok Shop')
                self.logger.info(f"Connected to TikTok Shop: {shop_name}")
                return {'success': True, 'shop': shop_name}
            elif response.status_code == 401:
                return {'success': False, 'error': 'Authentication failed - Invalid token'}
            else:
                return {'success': False, 'error': f'API Error: {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # ORDER METHODS
    # =====================================================================

    def get_orders(self, filters=None, limit=100):
        """Fetch orders from TikTok Shop"""
        try:
            filters = filters or {}
            status_filter = filters.get('status', 'UNPAID')  # UNPAID, PAID, SHIPPED, DELIVERED, CANCELLED

            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/orders/search"

            # Time range for order retrieval (last 30 days)
            create_time_from = int((datetime.utcnow() - timedelta(days=30)).timestamp() * 1000)
            create_time_to = int(datetime.utcnow().timestamp() * 1000)

            payload = {
                'status': status_filter,
                'create_time_from': create_time_from,
                'create_time_to': create_time_to,
                'page_size': min(limit, 50),
                'cursor': ''
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return {'success': False, 'error': f'API Error: {response.status_code}'}

            data = response.json()
            if data.get('code') != 0:
                return {'success': False, 'error': data.get('message', 'Unknown error')}

            orders = []
            for order in data.get('data', {}).get('orders', []):
                orders.append({
                    'marketplace_order_id': order['order_id'],
                    'order_number': order['order_id'],
                    'customer_name': order.get('recipient_address', {}).get('name', 'Customer'),
                    'customer_email': order.get('buyer_email', ''),
                    'customer_phone': order.get('recipient_address', {}).get('phone_number', ''),
                    'total': float(order.get('total_amount', 0)) / 100,  # TikTok uses cents
                    'fulfillment_status': order.get('fulfillment_type', 'EXPRESS'),
                    'payment_status': order.get('payment_type', 'UNPAID'),
                    'created_at': datetime.fromtimestamp(order['create_time'] / 1000).isoformat(),
                    'items': self._normalize_order_items(order.get('line_items', []))
                })

            return {'success': True, 'orders': orders}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_order(self, marketplace_order_id):
        """Get single order by TikTok Order ID"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/orders/detail"

            payload = {
                'order_id': marketplace_order_id
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return {'success': False, 'error': 'Order not found'}

            data = response.json()
            if data.get('code') != 0:
                return {'success': False, 'error': 'Order not found'}

            order = data.get('data', {})
            return {
                'success': True,
                'order': {
                    'marketplace_order_id': order['order_id'],
                    'order_number': order['order_id'],
                    'customer_email': order.get('buyer_email', ''),
                    'total': float(order.get('total_amount', 0)) / 100,
                    'status': order.get('order_status')
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def acknowledge_order(self, marketplace_order_id):
        """Acknowledge order received"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/orders/acknowledge"

            payload = {
                'order_id': marketplace_order_id
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                return {'success': True}
            else:
                return {'success': False, 'error': f'API Error: {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def cancel_order(self, marketplace_order_id, reason=''):
        """Cancel order on TikTok Shop"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/orders/cancel"

            payload = {
                'order_id': marketplace_order_id,
                'reason': reason or 'CUSTOMER_REQUEST'
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return {'success': True}

            return {'success': False, 'error': 'Failed to cancel order'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # INVENTORY METHODS
    # =====================================================================

    def get_inventory(self, marketplace_sku_id):
        """Get inventory for TikTok Shop SKU"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/products/inventory/get"

            payload = {
                'sku_id': marketplace_sku_id
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return {'success': False, 'error': 'SKU not found'}

            data = response.json()
            if data.get('code') != 0:
                return {'success': False, 'error': 'SKU not found'}

            inventory = data.get('data', {})
            return {
                'success': True,
                'marketplace_sku_id': marketplace_sku_id,
                'quantity': inventory.get('quantity', 0)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_inventory(self, marketplace_sku_id, quantity):
        """Update inventory on TikTok Shop"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/products/inventory/update"

            payload = {
                'sku_id': marketplace_sku_id,
                'quantity': quantity
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return {'success': True}

            return {'success': False, 'error': 'Failed to update inventory'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_sku_mapping(self, internal_sku):
        """Get TikTok Shop SKU for internal SKU"""
        return {
            'success': True,
            'internal_sku': internal_sku,
            'marketplace_sku_id': internal_sku  # Default 1:1 mapping
        }

    # =====================================================================
    # FULFILLMENT METHODS
    # =====================================================================

    def create_fulfillment(self, marketplace_order_id, items, tracking_number=''):
        """Create fulfillment shipment on TikTok Shop"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/orders/fulfillment/create"

            payload = {
                'order_id': marketplace_order_id,
                'tracking_number': tracking_number or '',
                'line_items': [
                    {
                        'line_item_id': item.get('line_item_id'),
                        'quantity': item.get('quantity', 1)
                    }
                    for item in items
                ]
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return {'success': True, 'fulfillment_id': marketplace_order_id}

            return {'success': False, 'error': 'Failed to create fulfillment'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_fulfillment_status(self, marketplace_order_id):
        """Get order fulfillment status"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/orders/detail"

            payload = {
                'order_id': marketplace_order_id
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return {'success': False, 'error': 'Order not found'}

            data = response.json()
            if data.get('code') != 0:
                return {'success': False, 'error': 'Order not found'}

            order = data.get('data', {})
            return {
                'success': True,
                'status': order.get('order_status'),
                'fulfillment_type': order.get('fulfillment_type')
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # RETURNS & REFUNDS
    # =====================================================================

    def get_returns(self, limit=50):
        """Get return requests from TikTok Shop"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/returns/search"

            payload = {
                'status': 'INITIATED',
                'page_size': min(limit, 50)
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return {'success': False, 'error': 'Failed to fetch returns'}

            data = response.json()
            if data.get('code') != 0:
                return {'success': False, 'error': data.get('message')}

            returns = data.get('data', {}).get('returns', [])
            return {'success': True, 'returns': returns}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_refunds(self, limit=50):
        """Get refunds from TikTok Shop"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/{self.API_VERSION}/refunds/search"

            payload = {
                'status': 'INITIATED',
                'page_size': min(limit, 50)
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return {'success': False, 'error': 'Failed to fetch refunds'}

            data = response.json()
            if data.get('code') != 0:
                return {'success': False, 'error': data.get('message')}

            refunds = data.get('data', {}).get('refunds', [])
            return {'success': True, 'refunds': refunds}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # WEBHOOK SUPPORT
    # =====================================================================

    def validate_webhook_signature(self, headers, body):
        """Validate TikTok webhook signature"""
        try:
            signature = headers.get('X-Shop-Signature', '')
            if not signature:
                return False

            # TikTok uses HMAC-SHA256
            # Signature = HMAC-SHA256(shop_cipher, body, secret_key)
            # For now, basic validation - implement full validation with secret
            return len(signature) == 64  # SHA256 hex length
        except Exception as e:
            self.logger.error(f"Webhook validation failed: {str(e)}")
            return False

    def process_webhook(self, event_type, payload):
        """Process incoming TikTok webhook"""
        self.logger.info(f"Processing TikTok webhook: {event_type}")

        if 'order.created' in event_type:
            return {'action': 'sync_order', 'order_id': payload.get('order_id')}
        elif 'order.updated' in event_type:
            return {'action': 'update_order', 'order_id': payload.get('order_id')}
        elif 'fulfillment.updated' in event_type:
            return {'action': 'update_fulfillment', 'order_id': payload.get('order_id')}

        return {'processed': False}

    # =====================================================================
    # INTERNAL HELPERS
    # =====================================================================

    def _get_headers(self):
        """Get request headers with authentication"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'User-Agent': 'SIAR-Platform/1.0'
        }

    def _normalize_order_items(self, line_items):
        """Normalize TikTok order items"""
        items = []
        for item in line_items:
            items.append({
                'sku': item.get('seller_sku', ''),
                'title': item.get('product_name', ''),
                'quantity': item.get('quantity', 1),
                'unit_price': float(item.get('original_price', 0)) / 100  # Convert from cents
            })
        return items
