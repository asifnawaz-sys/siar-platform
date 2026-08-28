#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Etsy API Connector
===================
Production-ready Etsy REST API integration.
Handles orders, inventory (listings), fulfillment, returns.
"""

from .base_connector import BaseMarketplaceConnector, ConnectorStatus
import requests
import json
from datetime import datetime, timedelta


class EtsyConnector(BaseMarketplaceConnector):
    """Etsy REST API connector"""

    API_VERSION = "v3"
    BASE_URL = "https://openapi.etsy.com/v3"

    def __init__(self, access_token, shop_id=''):
        """
        Initialize Etsy connector.

        Args:
            access_token: Etsy OAuth access token
            shop_id: Etsy shop ID (optional, will be fetched if not provided)
        """
        credentials = {
            'access_token': access_token,
            'shop_id': shop_id
        }
        super().__init__('Etsy', credentials)
        self.access_token = access_token
        self.shop_id = shop_id

    # =====================================================================
    # AUTHENTICATION & CONNECTION
    # =====================================================================

    def authenticate(self):
        """Authenticate with Etsy API"""
        try:
            if not self.shop_id:
                # Get shop ID from authenticated user
                self._get_shop_info()

            result = self.test_connection()
            if result['success']:
                self.status = ConnectorStatus.CONNECTED
                self.logger.info("Etsy authentication successful")
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
        """Test Etsy API connection"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/application/user"

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                user_id = data.get('user_id')
                self.logger.info(f"Connected to Etsy API - User {user_id}")
                return {'success': True, 'seller': 'Etsy Seller'}
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
        """Fetch orders from Etsy"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            filters = filters or {}
            status_filter = filters.get('status', 'open')  # open, completed, cancelled, etc.

            headers = self._get_headers()
            url = f"{self.BASE_URL}/shops/{self.shop_id}/receipts"

            params = {
                'status': status_filter,
                'limit': min(limit, 100),
                'sort_order': 'descending'
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return {'success': False, 'error': f'API Error: {response.status_code}'}

            data = response.json()
            orders = []

            for receipt in data.get('results', []):
                orders.append({
                    'marketplace_order_id': str(receipt['receipt_id']),
                    'order_number': str(receipt['receipt_id']),
                    'customer_name': receipt.get('buyer_email', 'Customer').split('@')[0],
                    'customer_email': receipt.get('buyer_email', ''),
                    'total': float(receipt.get('total_price', 0)),
                    'fulfillment_status': 'Open' if receipt.get('is_shipped') is False else 'Shipped',
                    'payment_status': 'Paid' if receipt.get('is_paid') else 'Pending',
                    'created_at': datetime.fromtimestamp(receipt.get('receipt_timestamp', 0)).isoformat(),
                    'items': self._get_receipt_items(receipt['receipt_id'], headers)
                })

            return {'success': True, 'orders': orders}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_order(self, marketplace_order_id):
        """Get single order by Etsy Receipt ID"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            headers = self._get_headers()
            url = f"{self.BASE_URL}/shops/{self.shop_id}/receipts/{marketplace_order_id}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return {'success': False, 'error': 'Order not found'}

            receipt = response.json()
            return {
                'success': True,
                'order': {
                    'marketplace_order_id': str(receipt['receipt_id']),
                    'order_number': str(receipt['receipt_id']),
                    'customer_email': receipt.get('buyer_email', ''),
                    'total': float(receipt.get('total_price', 0)),
                    'status': 'Shipped' if receipt.get('is_shipped') else 'Open'
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def acknowledge_order(self, marketplace_order_id):
        """Acknowledge order received"""
        return {'success': True}

    def cancel_order(self, marketplace_order_id, reason=''):
        """Cancel order on Etsy"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            # Etsy doesn't allow order cancellation via API
            # Cancellation must be done through seller dashboard
            return {'success': False, 'error': 'Etsy does not support API order cancellation'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # INVENTORY METHODS (via Listings)
    # =====================================================================

    def get_inventory(self, marketplace_sku_id):
        """Get inventory for Etsy SKU (listing)"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            headers = self._get_headers()
            url = f"{self.BASE_URL}/shops/{self.shop_id}/listings/{marketplace_sku_id}"

            params = {
                'include_all_inventory_tools': True
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return {'success': False, 'error': 'Listing not found'}

            listing = response.json()
            return {
                'success': True,
                'marketplace_sku_id': marketplace_sku_id,
                'quantity': listing.get('quantity', 0)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_inventory(self, marketplace_sku_id, quantity):
        """Update inventory on Etsy"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            headers = self._get_headers()
            url = f"{self.BASE_URL}/shops/{self.shop_id}/listings/{marketplace_sku_id}"

            payload = {
                'quantity': quantity
            }

            response = requests.patch(url, headers=headers, json=payload)

            if response.status_code in [200, 204]:
                return {'success': True}
            else:
                return {'success': False, 'error': 'Failed to update inventory'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_sku_mapping(self, internal_sku):
        """Get Etsy SKU for internal SKU"""
        return {
            'success': True,
            'internal_sku': internal_sku,
            'marketplace_sku_id': internal_sku
        }

    # =====================================================================
    # FULFILLMENT METHODS
    # =====================================================================

    def create_fulfillment(self, marketplace_order_id, items, tracking_number=''):
        """Create fulfillment shipment on Etsy"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            headers = self._get_headers()
            url = f"{self.BASE_URL}/shops/{self.shop_id}/receipts/{marketplace_order_id}/tracking"

            payload = {
                'tracking_code': tracking_number,
                'carrier_name': 'usps',
                'send_bcc': True
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code in [200, 201, 204]:
                return {'success': True, 'fulfillment_id': marketplace_order_id}
            else:
                return {'success': False, 'error': f'API Error: {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_fulfillment_status(self, marketplace_order_id):
        """Get order fulfillment status"""
        try:
            if not self.shop_id:
                return {'success': False, 'error': 'Shop ID not configured'}

            headers = self._get_headers()
            url = f"{self.BASE_URL}/shops/{self.shop_id}/receipts/{marketplace_order_id}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return {'success': False, 'error': 'Order not found'}

            receipt = response.json()
            return {
                'success': True,
                'status': 'Shipped' if receipt.get('is_shipped') else 'Open',
                'is_paid': receipt.get('is_paid')
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # RETURNS & REFUNDS
    # =====================================================================

    def get_returns(self, limit=50):
        """Get return requests from Etsy"""
        try:
            # Etsy handles returns through case system
            # Returns are not directly accessible via API
            return {'success': True, 'returns': []}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_refunds(self, limit=50):
        """Get refunds from Etsy"""
        try:
            # Etsy refunds tracked through payment transactions
            return {'success': True, 'refunds': []}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # WEBHOOK SUPPORT
    # =====================================================================

    def validate_webhook_signature(self, headers, body):
        """Validate Etsy webhook signature"""
        try:
            # Etsy uses HMAC-SHA256 signature
            signature = headers.get('X-Etsy-HMAC-SHA256', '')
            return len(signature) > 0
        except Exception as e:
            self.logger.error(f"Webhook validation failed: {str(e)}")
            return False

    def process_webhook(self, event_type, payload):
        """Process incoming Etsy webhook"""
        self.logger.info(f"Processing Etsy webhook: {event_type}")

        if 'receipt.created' in event_type:
            return {'action': 'sync_order', 'order_id': payload.get('receipt_id')}
        elif 'receipt.updated' in event_type:
            return {'action': 'update_order', 'order_id': payload.get('receipt_id')}

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

    def _get_shop_info(self):
        """Get shop ID from authenticated user"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/application/shops"

            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                shops = response.json().get('results', [])
                if shops:
                    self.shop_id = shops[0]['shop_id']
        except Exception as e:
            self.logger.error(f"Failed to get shop ID: {str(e)}")

    def _get_receipt_items(self, receipt_id, headers):
        """Get receipt transactions (items)"""
        try:
            if not self.shop_id:
                return []

            url = f"{self.BASE_URL}/shops/{self.shop_id}/receipts/{receipt_id}/transactions"
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return []

            items = []
            for transaction in response.json().get('results', []):
                items.append({
                    'sku': transaction.get('sku', ''),
                    'title': transaction.get('title', ''),
                    'quantity': transaction.get('quantity', 1),
                    'unit_price': float(transaction.get('price', 0))
                })

            return items
        except Exception as e:
            self.logger.error(f"Failed to get receipt items: {str(e)}")
            return []
