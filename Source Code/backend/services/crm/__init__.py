"""CRM Service"""

from .processor import get_processor
from .routes import crm_bp

__all__ = ['get_processor', 'crm_bp']
