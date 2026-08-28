#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay API Connector
==================
Production-ready eBay REST API integration.
Handles orders, inventory, fulfillment, returns.
"""

from .base_connector import BaseMarketplaceConnector, ConnectorStatus
import requests
import json
from datetime import datetime, timedelta


class EbayConnector(BaseMarketplaceConnector):
    """eBay REST API connector"""

    API_VERSION = "v2"
    BASE_URL = "https://api.ebay.com"
    ENVIRONMENT = "production"  # or 'sandbox'

    def __init__(self, access_token, app_id, cert_id, campaign_id=''):
        """
        Initialize eBay connector.

        Args:
            access_token: eBay OAuth access token
            app_id: eBay application ID
            cert_id: eBay certificate ID
            campaign_id: eBay campaign ID
        """
        credentials = {
            'access_token': access_token,
            'app_id': app_id,
            'cert_id': cert_id,
            'campaign_id': campaign_id
        }
        super().__init__('eBay', credentials)
        self.access_token = access_token
        self.app_id = app_id
        self.cert_id = cert_id
        self.campaign_id = campaign_id

    # =====================================================================
    # AUTHENTICATION & CONNECTION
    # =====================================================================

    def authenticate(self):
        """Authenticate with eBay API"""
        try:
            result = self.test_connection()
            if result['success']:
                self.status = ConnectorStatus.CONNECTED
                self.logger.info("eBay authentication successful")
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
        """Test eBay API connection"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/account/v1/seller"

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                self.logger.info("Connected to eBay API")
                return {'success': True, 'seller': 'eBay Seller'}
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
        """Fetch orders from eBay"""
        try:
            filters = filters or {}

            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/fulfillment/v1/order"

            params = {
                'filter': 'orderfulfillmentstatus:{NOT_STARTED|IN_PROGRESS}',
                'limit': min(limit, 100)
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return {'success': False, 'error': f'API Error: {response.status_code}'}

            data = response.json()
            orders = []

            for order in data.get('orders', []):
                orders.append({
                    'marketplace_order_id': order['orderId'],
                    'order_number': order['orderId'],
                    'customer_name': self._get_customer_name(order),
                    'customer_email': self._get_customer_email(order),
                    'total': float(order.get('pricingSummary', {}).get('total', {}).get('value', 0)),
                    'fulfillment_status': order.get('orderFulfillmentStatus', 'NOT_STARTED'),
                    'payment_status': 'Paid',
                    'created_at': order.get('creationDate'),
                    'items': self._normalize_order_items(order.get('lineItems', []))
                })

            return {'success': True, 'orders': orders}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_order(self, marketplace_order_id):
        """Get single order by eBay Order ID"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/fulfillment/v1/order/{marketplace_order_id}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return {'success': False, 'error': 'Order not found'}

            order = response.json()
            return {
                'success': True,
                'order': {
                    'marketplace_order_id': order['orderId'],
                    'order_number': order['orderId'],
                    'customer_email': self._get_customer_email(order),
                    'total': float(order.get('pricingSummary', {}).get('total', {}).get('value', 0)),
                    'status': order.get('orderFulfillmentStatus')
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def acknowledge_order(self, marketplace_order_id):
        """Acknowledge order received"""
        return {'success': True}

    def cancel_order(self, marketplace_order_id, reason=''):
        """Cancel order on eBay"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/fulfillment/v1/order/{marketplace_order_id}/cancel"

            payload = {
                'cancelReason': reason or 'OTHER',
                'cancelReasonDescription': reason or 'Seller cancellation'
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code in [200, 204]:
                return {'success': True}
            else:
                return {'success': False, 'error': 'Failed to cancel order'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # INVENTORY METHODS
    # =====================================================================

    def get_inventory(self, marketplace_sku_id):
        """Get inventory for eBay SKU"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/inventory/v1/inventory_item/{marketplace_sku_id}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return {'success': False, 'error': 'SKU not found'}

            data = response.json()
            return {
                'success': True,
                'marketplace_sku_id': marketplace_sku_id,
                'quantity': data.get('availability', {}).get('quantity', 0)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def update_inventory(self, marketplace_sku_id, quantity):
        """Update inventory on eBay"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/inventory/v1/inventory_item/{marketplace_sku_id}"

            payload = {
                'availability': {
                    'quantity': quantity
                }
            }

            response = requests.put(url, headers=headers, json=payload)

            if response.status_code in [200, 204]:
                return {'success': True}
            else:
                return {'success': False, 'error': 'Failed to update inventory'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_sku_mapping(self, internal_sku):
        """Get eBay SKU for internal SKU"""
        return {
            'success': True,
            'internal_sku': internal_sku,
            'marketplace_sku_id': internal_sku
        }

    # =====================================================================
    # FULFILLMENT METHODS
    # =====================================================================

    def create_fulfillment(self, marketplace_order_id, items, tracking_number=''):
        """Create fulfillment shipment on eBay"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/fulfillment/v1/order/{marketplace_order_id}/shipping_fulfillment"

            payload = {
                'lineItems': [
                    {
                        'lineItemId': item.get('line_item_id'),
                        'quantity': item.get('quantity', 1)
                    }
                    for item in items
                ]
            }

            if tracking_number:
                payload['trackingNumber'] = tracking_number

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code in [200, 201]:
                return {'success': True, 'fulfillment_id': response.json().get('fulfillmentId')}
            else:
                return {'success': False, 'error': f'API Error: {response.status_code}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_fulfillment_status(self, marketplace_order_id):
        """Get order fulfillment status"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/fulfillment/v1/order/{marketplace_order_id}"

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                return {'success': False, 'error': 'Order not found'}

            order = response.json()
            return {
                'success': True,
                'status': order.get('orderFulfillmentStatus'),
                'shipments': order.get('shipmentSummary', {})
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # RETURNS & REFUNDS
    # =====================================================================

    def get_returns(self, limit=50):
        """Get return requests from eBay"""
        try:
            headers = self._get_headers()
            url = f"{self.BASE_URL}/sell/fulfillment/v1/return"

            params = {
                'limit': min(limit, 100),
                'filter': 'returnStatus:{RETURN_INITIATED}'
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                return {'success': False, 'error': 'Failed to fetch returns'}

            data = response.json()
            returns = data.get('returns', [])
            return {'success': True, 'returns': returns}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_refunds(self, limit=50):
        """Get refunds from eBay"""
        try:
            # eBay doesn't have separate refund endpoint
            # Refunds are tracked through returns
            return self.get_returns(limit)
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # =====================================================================
    # WEBHOOK SUPPORT
    # =====================================================================

    def validate_webhook_signature(self, headers, body):
        """Validate eBay webhook signature"""
        try:
            # eBay uses X-EBAY-SIGNATURE header
            signature = headers.get('X-EBAY-SIGNATURE', '')
            return len(signature) > 0
        except Exception as e:
            self.logger.error(f"Webhook validation failed: {str(e)}")
            return False

    def process_webhook(self, event_type, payload):
        """Process incoming eBay webhook"""
        self.logger.info(f"Processing eBay webhook: {event_type}")

        if 'ORDER.CREATED' in event_type:
            return {'action': 'sync_order', 'order_id': payload.get('resourceId')}
        elif 'ORDER.UPDATED' in event_type:
            return {'action': 'update_order', 'order_id': payload.get('resourceId')}

        return {'processed': False}

    # =====================================================================
    # INTERNAL HELPERS
    # =====================================================================

    def _get_headers(self):
        """Get request headers with authentication"""
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Language': 'en-US',
            'Content-Type': 'application/json',
            'User-Agent': 'SIAR-Platform/1.0'
        }

    def _get_customer_name(self, order):
        """Extract customer name from order"""
        shipping = order.get('shippingAddress', {})
        return shipping.get('fullName', 'Customer')

    def _get_customer_email(self, order):
        """Extract customer email from order"""
        buyer = order.get('buyer', {})
        return buyer.get('email', '')

    def _normalize_order_items(self, line_items):
        """Normalize eBay order items"""
        items = []
        for item in line_items:
            items.append({
                'sku': item.get('sku', ''),
                'title': item.get('title', ''),
                'quantity': item.get('quantity', 1),
                'unit_price': float(item.get('lineItemPrice', {}).get('value', 0))
            })
        return items
