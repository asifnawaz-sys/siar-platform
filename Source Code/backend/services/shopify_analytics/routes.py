#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shopify Analytics & Reconciliation Service Integration
======================================================
API endpoints for Shopify Orders/Products Analytics and Data Reconciliation.
"""

from flask import Blueprint, request, jsonify, send_file
import os
import sys
import json
import base64
import tempfile
import shutil
import io
import zipfile
from datetime import datetime

# Get the service path
SERVICE_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SERVICE_PATH)

try:
    import shopify_analytics_app
    import recon_app
except ImportError as e:
    print(f"Warning: Could not import Shopify Analytics modules: {e}")

shopify_bp = Blueprint('shopify', __name__)

@shopify_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Shopify Analytics & Reconciliation',
        'version': '1.0',
        'features': ['analytics', 'reconciliation']
    }), 200

@shopify_bp.route('/analytics/upload', methods=['POST'])
def upload_analytics_files():
    """
    Upload Shopify Orders and Products CSV/Excel files.

    Expected JSON payload:
    {
        "ordersFile": {
            "name": "orders.csv",
            "b64": "base64_encoded_content"
        },
        "productsFile": {
            "name": "products.csv",
            "b64": "base64_encoded_content"
        },
        "outputFormat": "xlsx"  # or "pptx" for PowerPoint
    }

    Returns: {
        "success": true,
        "message": "Files processed successfully",
        "report_url": "/api/shopify/analytics/download/{session_id}",
        "session_id": "session_123"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON payload received'}), 400

        # Extract file information
        orders_file = data.get('ordersFile', {})
        products_file = data.get('productsFile', {})

        if not orders_file.get('b64') or not products_file.get('b64'):
            return jsonify({'error': 'Both Orders and Products files are required'}), 400

        # Create temporary directory for processing
        tmp_dir = tempfile.mkdtemp(prefix='shopify_analytics_')

        try:
            # Write uploaded files
            orders_path = os.path.join(tmp_dir, 'orders' + _get_file_ext(orders_file.get('name', '')))
            products_path = os.path.join(tmp_dir, 'products' + _get_file_ext(products_file.get('name', '')))

            with open(orders_path, 'wb') as f:
                f.write(base64.b64decode(orders_file.get('b64', '')))

            with open(products_path, 'wb') as f:
                f.write(base64.b64decode(products_file.get('b64', '')))

            # Create output directory
            output_dir = os.path.join(tmp_dir, 'output')
            os.makedirs(output_dir, exist_ok=True)

            # Generate analytics report
            output_path = os.path.join(output_dir, 'Shopify_Analytics_Report.xlsx')

            # Call the analytics generator
            shopify_analytics_app.main(orders_path, products_path, output_path)

            # Store the temporary directory reference for download
            session_id = os.path.basename(tmp_dir)

            # Store session info globally for retrieval
            if not hasattr(shopify_bp, '_sessions'):
                shopify_bp._sessions = {}
            shopify_bp._sessions[session_id] = {
                'tmp_dir': tmp_dir,
                'output_path': output_path,
                'timestamp': datetime.now()
            }

            return jsonify({
                'success': True,
                'message': 'Analytics report generated successfully',
                'session_id': session_id,
                'report_filename': 'Shopify_Analytics_Report.xlsx'
            }), 200

        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return jsonify({'error': f'Analytics generation failed: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'Request processing failed: {str(e)}'}), 500

@shopify_bp.route('/analytics/download/<session_id>', methods=['GET'])
def download_analytics_report(session_id):
    """Download generated analytics report"""
    try:
        if not hasattr(shopify_bp, '_sessions') or session_id not in shopify_bp._sessions:
            return jsonify({'error': 'Session not found or expired'}), 404

        session = shopify_bp._sessions[session_id]
        output_path = session.get('output_path')

        if not os.path.isfile(output_path):
            return jsonify({'error': 'Report file not found'}), 404

        return send_file(
            output_path,
            as_attachment=True,
            download_name='Shopify_Analytics_Report.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@shopify_bp.route('/reconciliation/process', methods=['POST'])
def process_reconciliation():
    """
    Process data reconciliation between Reference and Final files.

    Expected JSON payload:
    {
        "referenceFile": {
            "name": "reference.csv",
            "b64": "base64_encoded_content"
        },
        "finalFile": {
            "name": "final.csv",
            "b64": "base64_encoded_content"
        },
        "brand": "Brand Name",
        "currency": "PKR",
        "generateExcel": true,
        "generatePPT": true
    }

    Returns: {
        "success": true,
        "message": "Reconciliation completed",
        "download_url": "/api/shopify/reconciliation/download/{session_id}",
        "session_id": "session_123"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No JSON payload received'}), 400

        # Extract file information
        reference_file = data.get('referenceFile', {})
        final_file = data.get('finalFile', {})
        brand = data.get('brand', 'Reconciliation Report')
        currency = data.get('currency', 'PKR')
        make_excel = data.get('generateExcel', True)
        make_ppt = data.get('generatePPT', True)

        if not reference_file.get('b64') or not final_file.get('b64'):
            return jsonify({'error': 'Both Reference and Final files are required'}), 400

        # Create temporary directory
        tmp_dir = tempfile.mkdtemp(prefix='shopify_recon_')

        try:
            # Write uploaded files
            ref_path = os.path.join(tmp_dir, 'reference' + _get_file_ext(reference_file.get('name', '')))
            final_path = os.path.join(tmp_dir, 'final' + _get_file_ext(final_file.get('name', '')))

            with open(ref_path, 'wb') as f:
                f.write(base64.b64decode(reference_file.get('b64', '')))

            with open(final_path, 'wb') as f:
                f.write(base64.b64decode(final_file.get('b64', '')))

            # Create output directory
            output_dir = os.path.join(tmp_dir, 'output')
            os.makedirs(output_dir, exist_ok=True)

            # Run reconciliation pipeline
            date_str = datetime.now().strftime("%d %B %Y")

            xlsx_path, pptx_path = recon_app.run_pipeline(
                final_path, None, ref_path, None, output_dir, brand,
                make_excel=make_excel, make_ppt=make_ppt,
                currency=currency, brand=brand, date_str=date_str, log=print,
                recalc=False
            )

            # Create zip file with results
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as z:
                if xlsx_path and os.path.isfile(xlsx_path):
                    z.write(xlsx_path, os.path.basename(xlsx_path))
                if pptx_path and os.path.isfile(pptx_path):
                    z.write(pptx_path, os.path.basename(pptx_path))

            zip_buffer.seek(0)

            # Store session info
            session_id = os.path.basename(tmp_dir)
            if not hasattr(shopify_bp, '_sessions'):
                shopify_bp._sessions = {}
            shopify_bp._sessions[session_id] = {
                'tmp_dir': tmp_dir,
                'zip_data': zip_buffer.getvalue(),
                'timestamp': datetime.now()
            }

            return jsonify({
                'success': True,
                'message': 'Reconciliation report generated successfully',
                'session_id': session_id,
                'download_filename': f'{brand} - Reconciliation.zip'
            }), 200

        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return jsonify({'error': f'Reconciliation processing failed: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'Request processing failed: {str(e)}'}), 500

@shopify_bp.route('/reconciliation/download/<session_id>', methods=['GET'])
def download_reconciliation_report(session_id):
    """Download generated reconciliation report (zip file)"""
    try:
        if not hasattr(shopify_bp, '_sessions') or session_id not in shopify_bp._sessions:
            return jsonify({'error': 'Session not found or expired'}), 404

        session = shopify_bp._sessions[session_id]
        zip_data = session.get('zip_data')

        if not zip_data:
            return jsonify({'error': 'Report file not found'}), 404

        return send_file(
            io.BytesIO(zip_data),
            as_attachment=True,
            download_name='Reconciliation_Report.zip',
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

@shopify_bp.route('/excel-to-csv', methods=['POST'])
def excel_to_csv():
    """
    Convert uploaded Excel file to CSV format.
    Supports .xlsx, .xls files.

    Expected JSON payload:
    {
        "fileName": "file.xlsx",
        "b64": "base64_encoded_content"
    }

    Returns: CSV content as text
    """
    try:
        data = request.get_json()

        if not data or not data.get('b64'):
            return jsonify({'error': 'File content required'}), 400

        tmp_dir = tempfile.mkdtemp(prefix='excel_convert_')

        try:
            # Write uploaded file
            file_path = os.path.join(tmp_dir, 'input' + _get_file_ext(data.get('fileName', '')))

            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(data.get('b64', '')))

            # Convert using recon_app's read_table function
            header, data_rows = recon_app.read_table(file_path)

            # Build CSV
            import csv as csv_module
            csv_buffer = io.StringIO()
            writer = csv_module.writer(csv_buffer)
            writer.writerow(header)
            for row in data_rows:
                writer.writerow([_cell_to_str(c) for c in row])

            return jsonify({
                'success': True,
                'csv_content': csv_buffer.getvalue()
            }), 200

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

@shopify_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get Shopify Analytics service statistics"""
    try:
        session_count = len(shopify_bp._sessions) if hasattr(shopify_bp, '_sessions') else 0

        return jsonify({
            'service': 'Shopify Analytics & Reconciliation',
            'status': 'operational',
            'active_sessions': session_count,
            'features': {
                'analytics': {
                    'description': 'Shopify Orders & Products Analytics',
                    'inputs': ['Orders CSV/Excel', 'Products CSV/Excel'],
                    'outputs': ['Excel Report with KPIs, Charts, Trends']
                },
                'reconciliation': {
                    'description': 'Data Reconciliation between Reference and Final files',
                    'inputs': ['Reference File (CSV/Excel)', 'Final File (CSV/Excel)'],
                    'outputs': ['Excel Report + PowerPoint with Discrepancies']
                }
            },
            'timestamp': datetime.now().isoformat()
        }), 200

    except Exception as e:
        return jsonify({'error': f'Stats retrieval failed: {str(e)}'}), 500

def _get_file_ext(filename):
    """Extract file extension from filename"""
    _, ext = os.path.splitext(filename or '')
    if ext.lower() not in ['.csv', '.xlsx', '.xls', '.txt', '.tsv']:
        ext = '.csv'
    return ext

def _cell_to_str(cell):
    """Convert cell value to string for CSV output"""
    if cell is None:
        return ''
    if isinstance(cell, bool):
        return 'true' if cell else 'false'
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell)
