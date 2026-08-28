"""CRM Business Logic and API Handler"""

from sqlalchemy import create_engine, or_, and_
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta
from .models import Contact, Lead, Task, Communication, CrmSetting, Base
import json
import csv
from io import StringIO
from pathlib import Path


class CRMProcessor:
    """CRM Core Functionality"""

    def __init__(self, db_path="data/database/crm.db"):
        """Initialize CRM with database"""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_session(self):
        """Get database session"""
        return self.Session()

    # ==================== CONTACT OPERATIONS ====================

    def create_contact(self, data):
        """Create new contact"""
        session = self.get_session()
        try:
            contact = Contact(
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                email=data.get('email'),
                phone=data.get('phone'),
                company=data.get('company'),
                title=data.get('title'),
                address=data.get('address'),
                city=data.get('city'),
                state=data.get('state'),
                zip_code=data.get('zip_code'),
                country=data.get('country'),
                notes=data.get('notes'),
                status=data.get('status', 'active')
            )
            session.add(contact)
            session.commit()
            result = contact.to_dict()
            session.close()
            return result
        except Exception as e:
            session.close()
            raise Exception(f"Error creating contact: {str(e)}")

    def get_contact(self, contact_id):
        """Get contact by ID"""
        session = self.get_session()
        contact = session.query(Contact).filter_by(id=contact_id).first()
        session.close()
        return contact.to_dict() if contact else None

    def list_contacts(self, search=None, status=None, limit=100, offset=0):
        """List all contacts with optional search and filtering"""
        session = self.get_session()
        query = session.query(Contact)

        if status:
            query = query.filter_by(status=status)

        if search:
            search_term = f"%{search}%"
            query = query.filter(or_(
                Contact.first_name.ilike(search_term),
                Contact.last_name.ilike(search_term),
                Contact.email.ilike(search_term),
                Contact.company.ilike(search_term),
                Contact.phone.ilike(search_term)
            ))

        total = query.count()
        contacts = [c.to_dict() for c in query.offset(offset).limit(limit).all()]
        session.close()

        return {
            'total': total,
            'contacts': contacts,
            'offset': offset,
            'limit': limit
        }

    def update_contact(self, contact_id, data):
        """Update contact"""
        session = self.get_session()
        contact = session.query(Contact).filter_by(id=contact_id).first()

        if not contact:
            session.close()
            return None

        for key, value in data.items():
            if hasattr(contact, key):
                setattr(contact, key, value)

        contact.updated_at = datetime.utcnow()
        session.commit()
        result = contact.to_dict()
        session.close()
        return result

    def delete_contact(self, contact_id):
        """Delete contact"""
        session = self.get_session()
        contact = session.query(Contact).filter_by(id=contact_id).first()

        if contact:
            session.delete(contact)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # ==================== LEAD OPERATIONS ====================

    def create_lead(self, data):
        """Create new lead"""
        session = self.get_session()
        try:
            lead = Lead(
                contact_id=data.get('contact_id'),
                title=data.get('title'),
                description=data.get('description'),
                value=data.get('value', 0.0),
                stage=data.get('stage', 'new'),
                probability=data.get('probability', 0.0),
                expected_close_date=self._parse_date(data.get('expected_close_date')),
                source=data.get('source'),
                status=data.get('status', 'active'),
                assigned_to=data.get('assigned_to')
            )
            session.add(lead)
            session.commit()
            result = lead.to_dict()
            session.close()
            return result
        except Exception as e:
            session.close()
            raise Exception(f"Error creating lead: {str(e)}")

    def get_lead(self, lead_id):
        """Get lead by ID"""
        session = self.get_session()
        lead = session.query(Lead).filter_by(id=lead_id).first()
        session.close()
        return lead.to_dict() if lead else None

    def list_leads(self, stage=None, status=None, limit=100, offset=0):
        """List leads with filtering"""
        session = self.get_session()
        query = session.query(Lead)

        if stage:
            query = query.filter_by(stage=stage)
        if status:
            query = query.filter_by(status=status)

        total = query.count()
        leads = [l.to_dict() for l in query.offset(offset).limit(limit).all()]
        session.close()

        return {
            'total': total,
            'leads': leads,
            'offset': offset,
            'limit': limit
        }

    def update_lead(self, lead_id, data):
        """Update lead"""
        session = self.get_session()
        lead = session.query(Lead).filter_by(id=lead_id).first()

        if not lead:
            session.close()
            return None

        for key, value in data.items():
            if key == 'expected_close_date':
                value = self._parse_date(value)
            if hasattr(lead, key):
                setattr(lead, key, value)

        lead.updated_at = datetime.utcnow()
        session.commit()
        result = lead.to_dict()
        session.close()
        return result

    def delete_lead(self, lead_id):
        """Delete lead"""
        session = self.get_session()
        lead = session.query(Lead).filter_by(id=lead_id).first()

        if lead:
            session.delete(lead)
            session.commit()
            session.close()
            return True
        session.close()
        return False

    # ==================== TASK OPERATIONS ====================

    def create_task(self, data):
        """Create new task"""
        session = self.get_session()
        try:
            task = Task(
                contact_id=data.get('contact_id'),
                title=data.get('title'),
                description=data.get('description'),
                task_type=data.get('task_type'),
                status=data.get('status', 'open'),
                priority=data.get('priority', 'medium'),
                due_date=self._parse_date(data.get('due_date')),
                assigned_to=data.get('assigned_to')
            )
            session.add(task)
            session.commit()
            result = task.to_dict()
            session.close()
            return result
        except Exception as e:
            session.close()
            raise Exception(f"Error creating task: {str(e)}")

    def get_task(self, task_id):
        """Get task by ID"""
        session = self.get_session()
        task = session.query(Task).filter_by(id=task_id).first()
        session.close()
        return task.to_dict() if task else None

    def list_tasks(self, status=None, contact_id=None, limit=100, offset=0):
        """List tasks with filtering"""
        session = self.get_session()
        query = session.query(Task)

        if status:
            query = query.filter_by(status=status)
        if contact_id:
            query = query.filter_by(contact_id=contact_id)

        total = query.count()
        tasks = [t.to_dict() for t in query.offset(offset).limit(limit).all()]
        session.close()

        return {
            'total': total,
            'tasks': tasks,
            'offset': offset,
            'limit': limit
        }

    def update_task(self, task_id, data):
        """Update task"""
        session = self.get_session()
        task = session.query(Task).filter_by(id=task_id).first()

        if not task:
            session.close()
            return None

        for key, value in data.items():
            if key in ['due_date', 'completed_date']:
                value = self._parse_date(value)
            if hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.utcnow()
        session.commit()
        result = task.to_dict()
        session.close()
        return result

    def complete_task(self, task_id):
        """Mark task as completed"""
        return self.update_task(task_id, {
            'status': 'completed',
            'completed_date': datetime.utcnow()
        })

    # ==================== COMMUNICATION OPERATIONS ====================

    def create_communication(self, data):
        """Log communication"""
        session = self.get_session()
        try:
            comm = Communication(
                contact_id=data.get('contact_id'),
                comm_type=data.get('comm_type'),
                subject=data.get('subject'),
                message=data.get('message'),
                direction=data.get('direction'),
                status=data.get('status'),
                recipient=data.get('recipient'),
                duration_minutes=data.get('duration_minutes'),
                notes=data.get('notes')
            )
            session.add(comm)
            session.commit()
            result = comm.to_dict()
            session.close()
            return result
        except Exception as e:
            session.close()
            raise Exception(f"Error logging communication: {str(e)}")

    def get_communications(self, contact_id, limit=50):
        """Get communication history for contact"""
        session = self.get_session()
        comms = session.query(Communication)\
            .filter_by(contact_id=contact_id)\
            .order_by(Communication.created_at.desc())\
            .limit(limit).all()
        result = [c.to_dict() for c in comms]
        session.close()
        return result

    # ==================== REPORTING ====================

    def get_dashboard_stats(self):
        """Get CRM dashboard statistics"""
        session = self.get_session()

        total_contacts = session.query(Contact).count()
        active_contacts = session.query(Contact).filter_by(status='active').count()
        total_leads = session.query(Lead).count()
        open_leads = session.query(Lead).filter_by(stage='new').count()
        open_tasks = session.query(Task).filter_by(status='open').count()
        overdue_tasks = session.query(Task).filter(
            Task.status != 'completed',
            Task.due_date < datetime.utcnow()
        ).count()

        # Revenue forecast
        leads = session.query(Lead).all()
        total_pipeline = sum([l.value * (l.probability / 100.0) for l in leads])

        session.close()

        return {
            'total_contacts': total_contacts,
            'active_contacts': active_contacts,
            'total_leads': total_leads,
            'open_leads': open_leads,
            'open_tasks': open_tasks,
            'overdue_tasks': overdue_tasks,
            'revenue_pipeline': total_pipeline
        }

    def export_contacts_csv(self):
        """Export all contacts to CSV"""
        session = self.get_session()
        contacts = session.query(Contact).all()

        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Company',
                        'Title', 'City', 'State', 'Country', 'Status', 'Created Date'])

        # Write data
        for contact in contacts:
            writer.writerow([
                contact.id,
                contact.first_name,
                contact.last_name,
                contact.email,
                contact.phone,
                contact.company,
                contact.title,
                contact.city,
                contact.state,
                contact.country,
                contact.status,
                contact.created_at.isoformat() if contact.created_at else ''
            ])

        session.close()
        return output.getvalue()

    def import_contacts_csv(self, csv_content):
        """Import contacts from CSV"""
        session = self.get_session()
        reader = csv.DictReader(StringIO(csv_content))

        imported = 0
        for row in reader:
            try:
                contact = Contact(
                    first_name=row.get('First Name'),
                    last_name=row.get('Last Name'),
                    email=row.get('Email'),
                    phone=row.get('Phone'),
                    company=row.get('Company'),
                    title=row.get('Title'),
                    city=row.get('City'),
                    state=row.get('State'),
                    country=row.get('Country'),
                    status=row.get('Status', 'active')
                )
                session.add(contact)
                imported += 1
            except Exception as e:
                print(f"Error importing row: {str(e)}")
                continue

        session.commit()
        session.close()
        return imported

    # ==================== UTILITY METHODS ====================

    def _parse_date(self, date_str):
        """Parse date string"""
        if not date_str:
            return None
        if isinstance(date_str, datetime):
            return date_str
        try:
            return datetime.fromisoformat(date_str)
        except:
            return None


# Global processor instance
_crm_processor = None


def get_processor(db_path="data/database/crm.db"):
    """Get or create CRM processor"""
    global _crm_processor
    if _crm_processor is None:
        _crm_processor = CRMProcessor(db_path)
    return _crm_processor
