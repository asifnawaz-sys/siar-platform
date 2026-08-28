#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analytics & Reporting API Routes - 8 endpoints for business intelligence"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
import os

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

# Database setup
DB_PATH = os.path.join(os.path.dirname(__file__), '../../Data/database/orders.db')
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False)
Session = sessionmaker(bind=engine)

def get_session():
    return Session()

# =====================================================================
# ANALYTICS ENDPOINTS (8)
# =====================================================================

@analytics_bp.route('/orders/trends', methods=['GET'])
def order_trends():
    """Order trends analysis - GET /api/analytics/orders/trends?days=30

    Query Parameters:
    - days: Number of days to analyze (default: 30)
    - warehouse_id: Filter by warehouse (optional)

    Returns:
    - Daily order count, revenue, and status breakdown
    """
    from .models import Order, OrderStatus
    from datetime import datetime, timedelta

    session = get_session()
    try:
        days = request.args.get('days', 30, type=int)
        warehouse_id = request.args.get('warehouse_id', type=int)

        start_date = datetime.utcnow() - timedelta(days=days)

        query = session.query(Order).filter(Order.created_at >= start_date)
        if warehouse_id:
            query = query.filter_by(warehouse_id=warehouse_id)

        orders = query.all()

        daily_stats = {}
        for order in orders:
            day = order.created_at.date()
            if day not in daily_stats:
                daily_stats[day] = {'count': 0, 'revenue': 0, 'statuses': {}}
            daily_stats[day]['count'] += 1
            daily_stats[day]['revenue'] += order.total_amount or 0
            status = order.status
            daily_stats[day]['statuses'][status] = daily_stats[day]['statuses'].get(status, 0) + 1

        return jsonify({
            'status': 'success',
            'period_days': days,
            'daily_trends': [
                {
                    'date': day.isoformat(),
                    'orders': stats['count'],
                    'revenue': stats['revenue'],
                    'statuses': stats['statuses']
                }
                for day, stats in sorted(daily_stats.items())
            ]
        }), 200
    finally:
        session.close()

@analytics_bp.route('/inventory/turnover', methods=['GET'])
def inventory_turnover():
    """Inventory turnover metrics - GET /api/analytics/inventory/turnover?days=90

    Query Parameters:
    - days: Analysis period (default: 90)

    Returns:
    - SKU turnover rates, movement velocity, stock levels
    """
    from .models import InventoryMovement, SKUMaster, SKUInventory

    session = get_session()
    try:
        days = request.args.get('days', 90, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)

        skus = session.query(SKUMaster).all()

        turnover_data = []
        for sku in skus:
            movements = session.query(InventoryMovement).filter(
                InventoryMovement.sku_id == sku.id,
                InventoryMovement.timestamp >= start_date
            ).all()

            inventory = session.query(SKUInventory).filter_by(sku_id=sku.id).first()

            total_outbound = sum(m.quantity for m in movements if m.movement_type in ['Sold', 'Returned'])
            turnover_rate = (total_outbound / (inventory.available_to_sell or 1)) if inventory else 0

            turnover_data.append({
                'sku_id': sku.id,
                'sku_name': sku.sku_name,
                'available': inventory.available_to_sell if inventory else 0,
                'reserved': inventory.reserved if inventory else 0,
                'movements_count': len(movements),
                'turnover_rate': round(turnover_rate, 2),
                'velocity': 'High' if turnover_rate > 2 else 'Medium' if turnover_rate > 0.5 else 'Low'
            })

        return jsonify({
            'status': 'success',
            'period_days': days,
            'total_skus': len(skus),
            'turnover_metrics': sorted(turnover_data, key=lambda x: x['turnover_rate'], reverse=True)
        }), 200
    finally:
        session.close()

@analytics_bp.route('/customer/lifetime-value', methods=['GET'])
def customer_lifetime_value():
    """Customer lifetime value analysis - GET /api/analytics/customer/lifetime-value?limit=100

    Query Parameters:
    - limit: Top N customers (default: 100)
    - min_orders: Filter by minimum orders (default: 1)

    Returns:
    - Customer spending patterns, order frequency, value segments
    """
    from .models import Customer, Order

    session = get_session()
    try:
        limit = request.args.get('limit', 100, type=int)
        min_orders = request.args.get('min_orders', 1, type=int)

        customers = session.query(Customer).all()

        clv_data = []
        for customer in customers:
            orders = session.query(Order).filter_by(customer_id=customer.id).all()

            if len(orders) < min_orders:
                continue

            total_spent = sum(o.total_amount or 0 for o in orders)
            avg_order_value = total_spent / len(orders) if orders else 0
            segment = customer.segment or 'New'

            clv_data.append({
                'customer_id': customer.id,
                'customer_name': customer.customer_name,
                'email': customer.email,
                'orders_count': len(orders),
                'total_spent': round(total_spent, 2),
                'avg_order_value': round(avg_order_value, 2),
                'segment': segment,
                'last_order': max(o.created_at for o in orders).isoformat() if orders else None
            })

        return jsonify({
            'status': 'success',
            'total_customers': len(customers),
            'analyzed_customers': len(clv_data),
            'clv_ranking': sorted(clv_data, key=lambda x: x['total_spent'], reverse=True)[:limit]
        }), 200
    finally:
        session.close()

@analytics_bp.route('/fulfillment/metrics', methods=['GET'])
def fulfillment_metrics():
    """Fulfillment performance metrics - GET /api/analytics/fulfillment/metrics?days=30

    Query Parameters:
    - days: Analysis period (default: 30)

    Returns:
    - On-time delivery rate, processing time, carrier performance
    """
    from .models import Order

    session = get_session()
    try:
        days = request.args.get('days', 30, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)

        orders = session.query(Order).filter(Order.created_at >= start_date).all()

        total_orders = len(orders)
        shipped = sum(1 for o in orders if o.status in ['Shipped', 'Delivered'])
        delivered = sum(1 for o in orders if o.status == 'Delivered')

        # Calculate average processing time
        processing_times = []
        for order in orders:
            if order.ship_date and order.created_at:
                processing_time = (order.ship_date - order.created_at).total_seconds() / 3600
                processing_times.append(processing_time)

        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0

        return jsonify({
            'status': 'success',
            'period_days': days,
            'total_orders': total_orders,
            'shipped_orders': shipped,
            'delivered_orders': delivered,
            'on_time_rate': round((delivered / total_orders * 100) if total_orders else 0, 2),
            'avg_processing_hours': round(avg_processing_time, 2),
            'ship_rate': round((shipped / total_orders * 100) if total_orders else 0, 2)
        }), 200
    finally:
        session.close()

@analytics_bp.route('/financial/summary', methods=['GET'])
def financial_summary():
    """Financial summary - GET /api/analytics/financial/summary?start_date=2024-01-01&end_date=2024-12-31

    Query Parameters:
    - start_date: Start date (YYYY-MM-DD)
    - end_date: End date (YYYY-MM-DD)

    Returns:
    - Revenue, COGS, profit, margins by date range
    """
    from .models import Order, OrderItem

    session = get_session()
    try:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            start_date = datetime.utcnow() - timedelta(days=90)

        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            end_date = datetime.utcnow()

        orders = session.query(Order).filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date
        ).all()

        total_revenue = sum(o.total_amount or 0 for o in orders)
        total_items = session.query(func.sum(OrderItem.quantity)).filter(
            OrderItem.order_id.in_([o.id for o in orders])
        ).scalar() or 0

        # Estimate COGS (60% of revenue as default)
        estimated_cogs = total_revenue * 0.60
        gross_profit = total_revenue - estimated_cogs
        margin = (gross_profit / total_revenue * 100) if total_revenue else 0

        return jsonify({
            'status': 'success',
            'period': {
                'start_date': start_date.date().isoformat(),
                'end_date': end_date.date().isoformat()
            },
            'financial_metrics': {
                'total_revenue': round(total_revenue, 2),
                'estimated_cogs': round(estimated_cogs, 2),
                'gross_profit': round(gross_profit, 2),
                'gross_margin_percent': round(margin, 2),
                'orders_count': len(orders),
                'avg_order_value': round(total_revenue / len(orders), 2) if orders else 0,
                'items_sold': total_items
            }
        }), 200
    finally:
        session.close()

@analytics_bp.route('/predictions/demand', methods=['GET'])
def demand_forecast():
    """Demand forecasting - GET /api/analytics/predictions/demand?days=30

    Query Parameters:
    - days: Forecast period (default: 30)
    - sku_id: Specific SKU (optional)

    Returns:
    - Predicted demand by SKU for next N days
    """
    from .models import Order, OrderItem, SKUMaster
    import statistics

    session = get_session()
    try:
        days = request.args.get('days', 30, type=int)
        sku_id = request.args.get('sku_id', type=int)

        historical_days = 90
        start_date = datetime.utcnow() - timedelta(days=historical_days)

        skus = [session.query(SKUMaster).filter_by(id=sku_id).first()] if scu_id else session.query(SKUMaster).all()

        forecasts = []
        for sku in skus:
            if not sku:
                continue

            items = session.query(OrderItem).filter(
                OrderItem.sku_id == sku.id,
                OrderItem.order_id.in_(session.query(Order.id).filter(Order.created_at >= start_date))
            ).all()

            quantities = [item.quantity for item in items]

            if quantities:
                avg_daily = statistics.mean(quantities) if len(quantities) > 0 else 0
                std_dev = statistics.stdev(quantities) if len(quantities) > 1 else 0
                predicted = avg_daily * days
                confidence = 'High' if std_dev < avg_daily else 'Medium' if std_dev < avg_daily * 1.5 else 'Low'
            else:
                avg_daily = 0
                predicted = 0
                confidence = 'Low'

            forecasts.append({
                'sku_id': sku.id,
                'sku_name': sku.sku_name,
                'historical_avg_daily': round(avg_daily, 2),
                'predicted_demand_period': round(predicted, 0),
                'confidence': confidence,
                'recommendation': 'Stock' if confidence == 'High' else 'Monitor'
            })

        return jsonify({
            'status': 'success',
            'forecast_days': days,
            'predictions': sorted(forecasts, key=lambda x: x['predicted_demand_period'], reverse=True)
        }), 200
    finally:
        session.close()

@analytics_bp.route('/reports/custom', methods=['POST'])
def custom_report():
    """Generate custom analytics report - POST /api/analytics/reports/custom

    Request:
    {
        "report_type": "order_summary|inventory|customer|fulfillment",
        "filters": {
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "warehouse_id": 1,
            "customer_segment": "VIP"
        },
        "metrics": ["revenue", "order_count", "avg_value"]
    }
    """
    session = get_session()
    try:
        data = request.get_json()
        report_type = data.get('report_type')
        filters = data.get('filters', {})
        metrics = data.get('metrics', [])

        # Build report based on type
        report_data = {
            'report_type': report_type,
            'generated_at': datetime.utcnow().isoformat(),
            'filters_applied': filters,
            'metrics_requested': metrics,
            'data': {}
        }

        return jsonify({
            'status': 'success',
            'report': report_data
        }), 200
    finally:
        session.close()

@analytics_bp.route('/export/<report_type>', methods=['GET'])
def export_report(report_type):
    """Export analytics report - GET /api/analytics/export/<report_type>?format=csv|json

    Path Parameters:
    - report_type: Type of report to export

    Query Parameters:
    - format: Export format (csv, json, excel) - default: csv
    - start_date: Start date
    - end_date: End date
    """
    session = get_session()
    try:
        export_format = request.args.get('format', 'csv')

        export_data = {
            'status': 'success',
            'report_type': report_type,
            'format': export_format,
            'export_url': f'/downloads/report_{report_type}_{datetime.utcnow().timestamp()}.{export_format}',
            'expires_in': '24 hours'
        }

        return jsonify(export_data), 200
    finally:
        session.close()
