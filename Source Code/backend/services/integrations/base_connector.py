#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Marketplace Connector Framework
====================================
Abstract base class for all marketplace integrations.
Ensures consistent API, error handling, and audit logging.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConnectorStatus(Enum):
    """Connector health status"""
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    ERROR = "Error"
    TOKEN_EXPIRED = "Token Expired"
    RATE_LIMITED = "Rate Limited"
    NOT_CONFIGURED = "Not Configured"


class SyncStatus(Enum):
    """Synchronization status"""
    IDLE = "Idle"
    SYNCING = "Syncing"
    SUCCESS = "Success"
    FAILED = "Failed"
    PARTIAL_FAILURE = "Partial Failure"


class BaseMarketplaceConnector(ABC):
    """
    Abstract base class for marketplace integrations.
    Every marketplace adapter must inherit from this.
    """

    def __init__(self, marketplace_name, credentials=None, logger=None):
        self.marketplace_name = marketplace_name
        self.credentials = credentials or {}
        self.logger = logger or logging.getLogger(self.marketplace_name)
        self.status = ConnectorStatus.NOT_CONFIGURED
        self.last_sync = None
        self.sync_status = SyncStatus.IDLE
        self.error_message = None
        self.sync_logs = []

    # =====================================================================
    # AUTHENTICATION & CONNECTION
    # =====================================================================

    @abstractmethod
    def authenticate(self):
        """Authenticate with marketplace API"""
        pass

    @abstractmethod
    def test_connection(self):
        """Test API connection"""
        pass

    def get_status(self):
        """Get connector status"""
        return {
            'marketplace': self.marketplace_name,
            'status': self.status.value,
            'last_sync': self.last_sync.isoformat() if self.last_sync else None,
            'sync_status': self.sync_status.value,
            'error_message': self.error_message
        }

    # =====================================================================
    # ORDER METHODS (Must implement all)
    # =====================================================================

    @abstractmethod
    def get_orders(self, filters=None, limit=100):
        """
        Fetch orders from marketplace.
        Returns:
        {
            'success': bool,
            'orders': [
                {
                    'marketplace_order_id': str,
                    'marketplace_sku_id': str,
                    'customer_name': str,
                    'customer_email': str,
                    'total': float,
                    'status': str,
                    'created_at': datetime,
                    'items': [...]
                }
            ],
            'error': str (if applicable)
        }
        """
        pass

    @abstractmethod
    def get_order(self, marketplace_order_id):
        """Get single order by marketplace order ID"""
        pass

    @abstractmethod
    def acknowledge_order(self, marketplace_order_id):
        """Acknowledge order receipt to marketplace"""
        pass

    @abstractmethod
    def cancel_order(self, marketplace_order_id, reason=''):
        """Cancel order on marketplace"""
        pass

    # =====================================================================
    # INVENTORY METHODS
    # =====================================================================

    @abstractmethod
    def get_inventory(self, marketplace_sku_id):
        """Get SKU inventory from marketplace"""
        pass

    @abstractmethod
    def update_inventory(self, marketplace_sku_id, quantity):
        """Update SKU quantity on marketplace"""
        pass

    @abstractmethod
    def get_sku_mapping(self, internal_sku):
        """Get marketplace SKU ID for internal SKU"""
        pass

    # =====================================================================
    # FULFILLMENT METHODS
    # =====================================================================

    @abstractmethod
    def create_fulfillment(self, marketplace_order_id, items, tracking_number=''):
        """Create fulfillment/shipment"""
        pass

    @abstractmethod
    def get_fulfillment_status(self, marketplace_order_id):
        """Get fulfillment status"""
        pass

    # =====================================================================
    # RETURNS & REFUNDS
    # =====================================================================

    @abstractmethod
    def get_returns(self, limit=50):
        """Get return requests"""
        pass

    @abstractmethod
    def get_refunds(self, limit=50):
        """Get refunds"""
        pass

    # =====================================================================
    # SYNCHRONIZATION
    # =====================================================================

    def sync(self, sync_type='full'):
        """
        Master synchronization method.
        Handles orders, inventory, fulfillment, returns.
        """
        try:
            self.sync_status = SyncStatus.SYNCING
            self.logger.info(f"Starting {sync_type} sync for {self.marketplace_name}")

            results = {
                'orders_synced': 0,
                'inventory_synced': 0,
                'fulfillment_updated': 0,
                'returns_synced': 0,
                'errors': []
            }

            # Sync orders
            try:
                order_result = self._sync_orders()
                results['orders_synced'] = order_result
            except Exception as e:
                msg = f"Order sync failed: {str(e)}"
                self.logger.error(msg)
                results['errors'].append(msg)

            # Sync inventory
            try:
                inv_result = self._sync_inventory()
                results['inventory_synced'] = inv_result
            except Exception as e:
                msg = f"Inventory sync failed: {str(e)}"
                self.logger.error(msg)
                results['errors'].append(msg)

            # Sync returns
            try:
                returns_result = self._sync_returns()
                results['returns_synced'] = returns_result
            except Exception as e:
                msg = f"Returns sync failed: {str(e)}"
                self.logger.error(msg)
                results['errors'].append(msg)

            self.last_sync = datetime.utcnow()
            self.sync_status = SyncStatus.SUCCESS if not results['errors'] else SyncStatus.PARTIAL_FAILURE

            self._log_sync(results)
            return results

        except Exception as e:
            self.sync_status = SyncStatus.FAILED
            self.error_message = str(e)
            self.logger.error(f"Sync failed: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _sync_orders(self):
        """Internal order sync"""
        orders = self.get_orders(limit=500)
        if not orders.get('success'):
            raise Exception(orders.get('error', 'Failed to fetch orders'))
        return len(orders.get('orders', []))

    def _sync_inventory(self):
        """Internal inventory sync"""
        # Implemented in specific connectors
        return 0

    def _sync_returns(self):
        """Internal returns sync"""
        returns = self.get_returns(limit=100)
        if not returns.get('success'):
            raise Exception(returns.get('error', 'Failed to fetch returns'))
        return len(returns.get('returns', []))

    # =====================================================================
    # ERROR HANDLING & LOGGING
    # =====================================================================

    def handle_api_error(self, error_code, error_message):
        """
        Centralized API error handling.
        Handles rate limiting, token expiry, etc.
        """
        if error_code == 429:  # Rate limit
            self.status = ConnectorStatus.RATE_LIMITED
            self.logger.warning(f"Rate limited: {error_message}")
            return {'retry_after': 60}

        elif error_code == 401:  # Unauthorized
            self.status = ConnectorStatus.TOKEN_EXPIRED
            self.error_message = "Token expired. Please re-authenticate."
            self.logger.error(f"Authentication failed: {error_message}")
            return {'action': 'reauthenticate'}

        elif error_code >= 500:  # Server error
            self.status = ConnectorStatus.ERROR
            self.logger.error(f"Server error {error_code}: {error_message}")
            return {'retry': True, 'backoff': 300}

        elif error_code >= 400:  # Client error
            self.logger.error(f"Client error {error_code}: {error_message}")
            return {'retry': False}

        else:
            self.logger.error(f"Unknown error {error_code}: {error_message}")
            return {'retry': True}

    def _log_sync(self, result):
        """Log synchronization result"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'marketplace': self.marketplace_name,
            'status': self.sync_status.value,
            'result': result
        }
        self.sync_logs.append(log_entry)

        # Keep only last 100 logs
        if len(self.sync_logs) > 100:
            self.sync_logs = self.sync_logs[-100:]

    # =====================================================================
    # WEBHOOK SUPPORT (Optional)
    # =====================================================================

    def validate_webhook_signature(self, headers, body):
        """
        Validate webhook signature to ensure authenticity.
        Must be implemented in connectors supporting webhooks.
        """
        self.logger.warning("Webhook signature validation not implemented")
        return False

    def process_webhook(self, event_type, payload):
        """Process incoming webhook"""
        self.logger.info(f"Processing webhook: {event_type}")
        # Implemented in specific connectors
        pass

    # =====================================================================
    # UTILITY METHODS
    # =====================================================================

    def normalize_order(self, marketplace_order):
        """
        Normalize marketplace order to SIAR format.
        Override in specific connectors as needed.
        """
        return {
            'marketplace_order_id': marketplace_order.get('id'),
            'customer_name': marketplace_order.get('customer', {}).get('name'),
            'customer_email': marketplace_order.get('customer', {}).get('email'),
            'total': marketplace_order.get('total'),
            'status': marketplace_order.get('status'),
            'created_at': marketplace_order.get('created_at'),
            'items': marketplace_order.get('items', [])
        }

    def retry_with_backoff(self, func, max_retries=3, backoff_factor=2):
        """Retry function with exponential backoff"""
        import time
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = backoff_factor ** attempt
                self.logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s: {str(e)}")
                time.sleep(wait_time)
