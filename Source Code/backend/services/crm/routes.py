"""CRM API Routes"""

from flask import Blueprint, request, jsonify, send_file
from functools import wraps
from .processor import get_processor
from io import BytesIO

crm_bp = Blueprint('crm', __name__, url_prefix='/api/crm')

# Get processor
processor = get_processor()


def require_auth(f):
    """Simple auth check - can be enhanced"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Basic auth check - in production, use proper auth
        return f(*args, **kwargs)
    return decorated_function


# ==================== CONTACT ROUTES ====================

@crm_bp.route('/contacts', methods=['POST'])
@require_auth
def create_contact():
    """Create new contact"""
    try:
        data = request.get_json()
        contact = processor.create_contact(data)
        return jsonify({'success': True, 'contact': contact}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/contacts/<int:contact_id>', methods=['GET'])
@require_auth
def get_contact(contact_id):
    """Get contact"""
    try:
        contact = processor.get_contact(contact_id)
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        return jsonify({'success': True, 'contact': contact}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/contacts', methods=['GET'])
@require_auth
def list_contacts():
    """List contacts with search and filtering"""
    try:
        search = request.args.get('search')
        status = request.args.get('status')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        result = processor.list_contacts(search=search, status=status, limit=limit, offset=offset)
        return jsonify({'success': True, **result}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/contacts/<int:contact_id>', methods=['PUT'])
@require_auth
def update_contact(contact_id):
    """Update contact"""
    try:
        data = request.get_json()
        contact = processor.update_contact(contact_id, data)
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        return jsonify({'success': True, 'contact': contact}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/contacts/<int:contact_id>', methods=['DELETE'])
@require_auth
def delete_contact(contact_id):
    """Delete contact"""
    try:
        success = processor.delete_contact(contact_id)
        if not success:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        return jsonify({'success': True, 'message': 'Contact deleted'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== LEAD ROUTES ====================

@crm_bp.route('/leads', methods=['POST'])
@require_auth
def create_lead():
    """Create new lead"""
    try:
        data = request.get_json()
        lead = processor.create_lead(data)
        return jsonify({'success': True, 'lead': lead}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/leads/<int:lead_id>', methods=['GET'])
@require_auth
def get_lead(lead_id):
    """Get lead"""
    try:
        lead = processor.get_lead(lead_id)
        if not lead:
            return jsonify({'success': False, 'error': 'Lead not found'}), 404
        return jsonify({'success': True, 'lead': lead}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/leads', methods=['GET'])
@require_auth
def list_leads():
    """List leads with filtering"""
    try:
        stage = request.args.get('stage')
        status = request.args.get('status')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        result = processor.list_leads(stage=stage, status=status, limit=limit, offset=offset)
        return jsonify({'success': True, **result}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/leads/<int:lead_id>', methods=['PUT'])
@require_auth
def update_lead(lead_id):
    """Update lead"""
    try:
        data = request.get_json()
        lead = processor.update_lead(lead_id, data)
        if not lead:
            return jsonify({'success': False, 'error': 'Lead not found'}), 404
        return jsonify({'success': True, 'lead': lead}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/leads/<int:lead_id>', methods=['DELETE'])
@require_auth
def delete_lead(lead_id):
    """Delete lead"""
    try:
        success = processor.delete_lead(lead_id)
        if not success:
            return jsonify({'success': False, 'error': 'Lead not found'}), 404
        return jsonify({'success': True, 'message': 'Lead deleted'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== TASK ROUTES ====================

@crm_bp.route('/tasks', methods=['POST'])
@require_auth
def create_task():
    """Create new task"""
    try:
        data = request.get_json()
        task = processor.create_task(data)
        return jsonify({'success': True, 'task': task}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/tasks/<int:task_id>', methods=['GET'])
@require_auth
def get_task(task_id):
    """Get task"""
    try:
        task = processor.get_task(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        return jsonify({'success': True, 'task': task}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/tasks', methods=['GET'])
@require_auth
def list_tasks():
    """List tasks"""
    try:
        status = request.args.get('status')
        contact_id = request.args.get('contact_id', type=int)
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)

        result = processor.list_tasks(status=status, contact_id=contact_id, limit=limit, offset=offset)
        return jsonify({'success': True, **result}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/tasks/<int:task_id>', methods=['PUT'])
@require_auth
def update_task(task_id):
    """Update task"""
    try:
        data = request.get_json()
        task = processor.update_task(task_id, data)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        return jsonify({'success': True, 'task': task}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/tasks/<int:task_id>/complete', methods=['POST'])
@require_auth
def complete_task(task_id):
    """Mark task as completed"""
    try:
        task = processor.complete_task(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        return jsonify({'success': True, 'task': task}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== COMMUNICATION ROUTES ====================

@crm_bp.route('/communications', methods=['POST'])
@require_auth
def create_communication():
    """Log communication"""
    try:
        data = request.get_json()
        comm = processor.create_communication(data)
        return jsonify({'success': True, 'communication': comm}), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/communications/<int:contact_id>', methods=['GET'])
@require_auth
def get_communications(contact_id):
    """Get communication history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        comms = processor.get_communications(contact_id, limit=limit)
        return jsonify({'success': True, 'communications': comms}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== REPORTING ROUTES ====================

@crm_bp.route('/dashboard', methods=['GET'])
@require_auth
def get_dashboard():
    """Get CRM dashboard statistics"""
    try:
        stats = processor.get_dashboard_stats()
        return jsonify({'success': True, **stats}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/export/contacts', methods=['GET'])
@require_auth
def export_contacts():
    """Export contacts as CSV"""
    try:
        csv_content = processor.export_contacts_csv()
        return send_file(
            BytesIO(csv_content.encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name='contacts.csv'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@crm_bp.route('/import/contacts', methods=['POST'])
@require_auth
def import_contacts():
    """Import contacts from CSV"""
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        csv_content = file.read().decode('utf-8')
        imported = processor.import_contacts_csv(csv_content)
        return jsonify({'success': True, 'imported': imported}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ==================== HEALTH CHECK ====================

@crm_bp.route('/health', methods=['GET'])
def crm_health():
    """CRM service health check"""
    return jsonify({'success': True, 'service': 'crm', 'status': 'operational'}), 200
