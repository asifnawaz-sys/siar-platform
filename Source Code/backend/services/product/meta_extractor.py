"""
Meta Field Extractor
Extract and parse custom metadata fields from product data
"""

import logging
from typing import Dict, List, Any
import re
import json

log = logging.getLogger('siar.meta_extractor')

class MetaExtractor:
    """Extract custom metadata fields from products"""

    # Fabric-specific field patterns
    FABRIC_PATTERNS = {
        'fabric_type': [r'fabric\s*(?:type|:)\s*([^,\n]+)', r'(?:composition|material):\s*(.+?)(?:,|$)'],
        'weight': [r'weight\s*(?::|=)\s*(\d+(?:\.\d+)?)\s*(g|kg|grams|gsm)?'],
        'composition': [r'composition\s*(?::|=)\s*([^,\n]+)'],
        'care': [r'care\s*(?:instructions|:|=)\s*([^,\n]+)'],
        'origin': [r'(?:origin|made in)\s*(?::|=)\s*([^,\n]+)'],
        'size_range': [r'(?:size|available).*?(?:xs|s|m|l|xl|xxl|custom)'],
        'color_available': [r'(?:color|colours?|available.*?colors?)[\s:]*([^,\n]+)'],
        'price': [r'\$\d+\.?\d*|\d+\.?\d*\s*(?:pkr|usd|eur)'],
        'stock': [r'(?:stock|in stock|available)[\s:]*(\d+)']
    }

    def __init__(self):
        log.info("MetaExtractor initialized")

    def extract_from_product(self, product: Dict) -> Dict:
        """
        Extract metadata from product dictionary

        Args:
            product: Product data dictionary

        Returns:
            Dictionary with extracted metadata fields
        """
        metadata = {}

        # Extract from description
        description = product.get('description', '')
        if description:
            metadata.update(self._extract_from_text(description))

        # Extract from title
        title = product.get('title', '')
        if title:
            title_meta = self._extract_from_text(title)
            # Prioritize description over title
            for key, value in title_meta.items():
                if key not in metadata:
                    metadata[key] = value

        # Extract from custom fields if present
        for field in ['meta_fields', 'custom_fields', 'attributes']:
            if field in product:
                field_data = product[field]
                if isinstance(field_data, dict):
                    metadata.update(field_data)
                elif isinstance(field_data, list):
                    for item in field_data:
                        if isinstance(item, dict):
                            metadata.update(item)

        log.info(f"Extracted {len(metadata)} metadata fields")
        return metadata

    def _extract_from_text(self, text: str) -> Dict:
        """Extract metadata fields from text"""
        text = text.lower()
        extracted = {}

        for field_name, patterns in self.FABRIC_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    if isinstance(matches[0], tuple):
                        # Pattern with groups
                        extracted[field_name] = matches[0][0].strip()
                    else:
                        # Simple pattern
                        extracted[field_name] = matches[0].strip()
                    break

        return extracted

    def extract_batch(self, products: List[Dict]) -> List[Dict]:
        """Extract metadata from multiple products"""
        results = []
        for product in products:
            enriched = product.copy()
            enriched['extracted_metadata'] = self.extract_from_product(product)
            results.append(enriched)
        return results

    def normalize_fields(self, metadata: Dict) -> Dict:
        """Normalize extracted fields to standard format"""
        normalized = {}

        # Map common field names to standard names
        field_mapping = {
            'fabric_type': 'fabric_type',
            'material': 'fabric_type',
            'composition': 'composition',
            'weight': 'weight_gsm',
            'care': 'care_instructions',
            'origin': 'country_of_origin',
            'size': 'size_range',
            'color': 'colors_available'
        }

        for key, value in metadata.items():
            mapped_key = field_mapping.get(key, key)
            normalized[mapped_key] = value

        return normalized

    def validate_metadata(self, metadata: Dict) -> Dict:
        """Validate extracted metadata"""
        validation = {
            'valid_fields': [],
            'invalid_fields': [],
            'warnings': []
        }

        for key, value in metadata.items():
            if not value or value.lower() == 'unknown':
                validation['invalid_fields'].append(key)
            else:
                validation['valid_fields'].append(key)
                # Check for suspicious patterns
                if len(value) > 500:
                    validation['warnings'].append(f'{key}: very long value')

        return validation
