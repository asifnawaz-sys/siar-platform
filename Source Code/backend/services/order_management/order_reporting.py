#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Reporting & Status Tracking System
========================================
Comprehensive order lifecycle tracking with status-wise analytics.
"""

from datetime import datetime, timedelta
from sqlalchemy import func, desc
from .models import Order, OrderStatus, OrderHistory, InventoryMovement


class OrderReportingEngine:
    """Complete order reporting and analytics"""

    def __init__(self, db_session):
        self.db = db_session

    # =====================================================================
    # ORDER LIFECYCLE TRACKING
    # =====================================================================

    def get_order_lifecycle(self, order_id):
        """Get complete order lifecycle with all status transitions"""
        order = self.db.query(Order).filter_by(id=order_id).first()
        if not order:
            return None

        history = self.db.query(OrderHistory).filter_by(order_id=order_id).order_by(
            OrderHistory.created_at.asc()
        ).all()

        lifecycle = {
            'order_number': order.order_number,
            'marketplace': order.marketplace,
            'current_status': order.order_status.value if order.order_status else None,
            'current_payment_status': order.payment_status.value if order.payment_status else None,
            'created_at': order.created_at.isoformat() if order.created_at else None,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None,
            'timeline': []
        }

        # Build timeline
        previous_time = None
        for h in history:
            time_taken = None
            if previous_time:
                time_taken = (h.created_at - previous_time).total_seconds() / 3600  # Hours

            lifecycle['timeline'].append({
                'timestamp': h.created_at.isoformat() if h.created_at else None,
                'from_status': h.old_status,
                'to_status': h.new_status,
                'changed_by': h.changed_by,
                'reason': h.change_reason,
                'hours_in_previous_status': round(time_taken, 2) if time_taken else None
            })

            previous_time = h.created_at

        return lifecycle

    def get_status_wise_orders(self):
        """Get order count by status"""
        statuses = {
            'NEW': OrderStatus.NEW,
            'CONFIRMED': OrderStatus.CONFIRMED,
            'PAYMENT_VERIFIED': OrderStatus.PAYMENT_VERIFIED,
            'INVENTORY_RESERVED': OrderStatus.INVENTORY_RESERVED,
            'PICKING': OrderStatus.PICKING,
            'PICKED': OrderStatus.PICKED,
            'PACKING': OrderStatus.PACKING,
            'PACKED': OrderStatus.PACKED,
            'READY_FOR_DISPATCH': OrderStatus.READY_FOR_DISPATCH,
            'DISPATCHED': OrderStatus.DISPATCHED,
            'DELIVERED': OrderStatus.DELIVERED,
            'CANCELLED': OrderStatus.CANCELLED,
            'ON_HOLD': OrderStatus.ON_HOLD,
            'RETURNED': OrderStatus.RETURNED,
            'PARTIALLY_RETURNED': OrderStatus.PARTIALLY_RETURNED,
            'REFUNDED': OrderStatus.REFUNDED
        }

        status_counts = {}
        for name, status_enum in statuses.items():
            count = self.db.query(Order).filter_by(order_status=status_enum).count()
            status_counts[name] = count

        return status_counts

    def get_orders_by_status(self, status_name, limit=100):
        """Get all orders with specific status"""
        try:
            status_enum = OrderStatus[status_name.upper()]
        except KeyError:
            return {'error': f'Invalid status: {status_name}'}

        orders = self.db.query(Order).filter_by(
            order_status=status_enum
        ).order_by(desc(Order.created_at)).limit(limit).all()

        return [
            {
                'id': order.id,
                'order_number': order.order_number,
                'customer': order.customer_name,
                'marketplace': order.marketplace,
                'total': order.total,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'ordered_at': order.ordered_at.isoformat() if order.ordered_at else None
            }
            for order in orders
        ]

    # =====================================================================
    # ORDER CYCLE ANALYTICS
    # =====================================================================

    def get_order_cycle_metrics(self, days=30):
        """Get order metrics for last N days"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        metrics = {
            'period_days': days,
            'period_start': cutoff_date.isoformat(),
            'period_end': datetime.utcnow().isoformat()
        }

        # Total orders
        total_orders = self.db.query(Order).filter(
            Order.created_at >= cutoff_date
        ).count()
        metrics['total_orders'] = total_orders

        # Orders by status
        confirmed = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status == OrderStatus.CONFIRMED
        ).count()

        picked = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status == OrderStatus.PICKED
        ).count()

        packed = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status == OrderStatus.PACKED
        ).count()

        dispatched = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status == OrderStatus.DISPATCHED
        ).count()

        delivered = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status == OrderStatus.DELIVERED
        ).count()

        cancelled = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status == OrderStatus.CANCELLED
        ).count()

        returned = self.db.query(Order).filter(
            Order.created_at >= cutoff_date,
            Order.order_status.in_([OrderStatus.RETURNED, OrderStatus.PARTIALLY_RETURNED])
        ).count()

        metrics['statuses'] = {
            'confirmed': confirmed,
            'picked': picked,
            'packed': packed,
            'dispatched': dispatched,
            'delivered': delivered,
            'cancelled': cancelled,
            'returned': returned
        }

        # Calculate fulfillment rate
        fulfilled = delivered
        fulfillment_rate = (fulfilled / total_orders * 100) if total_orders > 0 else 0
        metrics['fulfillment_rate'] = round(fulfillment_rate, 2)

        # Calculate cancellation rate
        cancellation_rate = (cancelled / total_orders * 100) if total_orders > 0 else 0
        metrics['cancellation_rate'] = round(cancellation_rate, 2)

        # Calculate return rate
        return_rate = (returned / delivered * 100) if delivered > 0 else 0
        metrics['return_rate'] = round(return_rate, 2)

        return metrics

    # =====================================================================
    # TURNAROUND TIME ANALYSIS
    # =====================================================================

    def get_average_turnaround_times(self):
        """Calculate average time in each status"""
        history = self.db.query(OrderHistory).order_by(
            OrderHistory.created_at.asc()
        ).all()

        status_times = {}

        for i, h in enumerate(history[:-1]):
            current_time = h.created_at
            next_time = history[i + 1].created_at

            time_diff = (next_time - current_time).total_seconds() / 3600  # Hours

            status = h.new_status
            if status not in status_times:
                status_times[status] = []

            status_times[status].append(time_diff)

        # Calculate averages
        avg_times = {}
        for status, times in status_times.items():
            if times:
                avg_time = sum(times) / len(times)
                avg_times[status] = {
                    'average_hours': round(avg_time, 2),
                    'min_hours': round(min(times), 2),
                    'max_hours': round(max(times), 2),
                    'sample_count': len(times)
                }

        return avg_times

    # =====================================================================
    # MARKETPLACE ANALYTICS
    # =====================================================================

    def get_marketplace_stats(self, days=30):
        """Get order statistics by marketplace"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get all marketplaces
        marketplaces = self.db.query(Order.marketplace).distinct().all()

        stats = {}
        for (marketplace,) in marketplaces:
            if not marketplace:
                marketplace = 'Direct'

            # Orders from this marketplace
            orders = self.db.query(Order).filter(
                Order.marketplace == marketplace,
                Order.created_at >= cutoff_date
            ).all()

            total_orders = len(orders)
            total_revenue = sum(o.total for o in orders)
            delivered_count = len([o for o in orders if o.order_status == OrderStatus.DELIVERED])
            cancelled_count = len([o for o in orders if o.order_status == OrderStatus.CANCELLED])

            stats[marketplace] = {
                'total_orders': total_orders,
                'total_revenue': round(total_revenue, 2),
                'delivered': delivered_count,
                'cancelled': cancelled_count,
                'fulfillment_rate': round((delivered_count / total_orders * 100), 2) if total_orders > 0 else 0
            }

        return stats

    # =====================================================================
    # DAILY ORDER TRENDS
    # =====================================================================

    def get_daily_order_trends(self, days=30):
        """Get daily order creation/fulfillment trends"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        trends = {}
        for i in range(days):
            day = cutoff_date + timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            date_key = day_start.strftime('%Y-%m-%d')

            # Orders created this day
            created = self.db.query(Order).filter(
                Order.created_at >= day_start,
                Order.created_at < day_end
            ).count()

            # Orders delivered this day
            delivered = self.db.query(Order).filter(
                Order.delivered_date >= day_start,
                Order.delivered_date < day_end
            ).count()

            # Orders cancelled this day
            cancelled = self.db.query(Order).filter(
                Order.order_status == OrderStatus.CANCELLED,
                Order.updated_at >= day_start,
                Order.updated_at < day_end
            ).count()

            trends[date_key] = {
                'orders_created': created,
                'orders_delivered': delivered,
                'orders_cancelled': cancelled
            }

        return trends

    # =====================================================================
    # COMPREHENSIVE DASHBOARD
    # =====================================================================

    def get_full_dashboard(self, days=30):
        """Get complete order dashboard for reporting"""
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'status_counts': self.get_status_wise_orders(),
            'cycle_metrics': self.get_order_cycle_metrics(days),
            'turnaround_times': self.get_average_turnaround_times(),
            'marketplace_stats': self.get_marketplace_stats(days),
            'daily_trends': self.get_daily_order_trends(days)
        }

    # =====================================================================
    # STATUS TRANSITIONS
    # =====================================================================

    def get_status_transition_matrix(self, days=30):
        """Show which statuses transition to which"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        history = self.db.query(OrderHistory).filter(
            OrderHistory.created_at >= cutoff_date
        ).all()

        transitions = {}
        for h in history:
            from_status = h.old_status or 'INITIAL'
            to_status = h.new_status

            key = f"{from_status} → {to_status}"
            transitions[key] = transitions.get(key, 0) + 1

        return dict(sorted(transitions.items(), key=lambda x: x[1], reverse=True))

    # =====================================================================
    # ORDER PERFORMANCE
    # =====================================================================

    def get_slow_orders(self, threshold_hours=48):
        """Find orders taking longer than threshold to deliver"""
        history = self.db.query(OrderHistory).all()

        slow_orders = []
        for order_id, histories in self._group_by_order(history):
            total_time = None
            if histories:
                first_time = min(h.created_at for h in histories)
                last_time = max(h.created_at for h in histories)
                total_time = (last_time - first_time).total_seconds() / 3600

                if total_time and total_time > threshold_hours:
                    order = self.db.query(Order).filter_by(id=order_id).first()
                    if order:
                        slow_orders.append({
                            'order_number': order.order_number,
                            'hours_in_cycle': round(total_time, 2),
                            'current_status': order.order_status.value if order.order_status else None,
                            'created_at': order.created_at.isoformat() if order.created_at else None
                        })

        return sorted(slow_orders, key=lambda x: x['hours_in_cycle'], reverse=True)

    def _group_by_order(self, histories):
        """Group histories by order_id"""
        grouped = {}
        for h in histories:
            if h.order_id not in grouped:
                grouped[h.order_id] = []
            grouped[h.order_id].append(h)
        return grouped.items()
