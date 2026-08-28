"""
AI-Powered Platform Router
Automatically detects platform and routes to appropriate scraper engine
Integrates all custom scrapers with intelligent processing engine switching

Features:
- Multi-platform detection (Shopify, WooCommerce, WordPress, Magento, custom)
- Automatic processing engine selection
- Custom scraper integration
- AI-based platform classification
- Fallback chain for unknown platforms
"""

import logging
import json
from typing import Tuple, Dict, List, Optional
from urllib.parse import urlparse
import re

log = logging.getLogger('siar.platform_router')

class PlatformRouter:
    """Intelligent platform detection and engine routing"""

    # Platform signatures and markers
    PLATFORM_MARKERS = {
        'shopify': {
            'headers': ['x-shopify-shop-api-call-limit', 'server: shopify'],
            'patterns': [r'//cdn\.shopify\.com', r'/cdn/shop/', r'Shopify\.checkout'],
            'api_endpoints': ['/products.json', '/admin/api/products'],
            'confidence_weight': 0.95
        },
        'woocommerce': {
            'headers': ['woocommerce', 'wordpress'],
            'patterns': [r'wp-content/plugins/woocommerce', r'/wp-json/wc/v3/', r'woocommerce-js'],
            'api_endpoints': ['/wp-json/wc/v3/products', '/wp-api/'],
            'confidence_weight': 0.90
        },
        'wordpress': {
            'headers': ['wordpress', 'wp-version'],
            'patterns': [r'/wp-content/', r'/wp-admin/', r'wp-includes', r'class="wp-', r'id="wp-'],
            'api_endpoints': ['/wp-json/', '/rest-api/'],
            'confidence_weight': 0.85
        },
        'magento': {
            'headers': ['magento', 'x-magento'],
            'patterns': [r'var FORM_KEY', r'/media/catalog/', r'Magento', r'mage\.cookies'],
            'api_endpoints': ['/rest/v2/products', '/rest/default/v1/'],
            'confidence_weight': 0.85
        },
        'bigcommerce': {
            'headers': ['bigcommerce'],
            'patterns': [r'bigcommerce\.com', r'/cdn/s/', r'BigCommerce', r'storefront-product'],
            'api_endpoints': ['/api/v3/catalog/products', '/api/stores/'],
            'confidence_weight': 0.85
        },
        'wix': {
            'headers': ['x-wix', 'wix'],
            'patterns': [r'\.wix\.com', r'wix-code', r'wixClient'],
            'api_endpoints': ['/site/products'],
            'confidence_weight': 0.80
        },
        'squarespace': {
            'headers': ['squarespace'],
            'patterns': [r'\.squarespace\.com', r'squarespace-js', r'sqs-'],
            'api_endpoints': ['/api/'],
            'confidence_weight': 0.80
        },
        'custom_fabric': {
            'patterns': [r'fabric\.io', r'fabriciohq', r'custom-fabric'],
            'confidence_weight': 0.70
        },
        'ansab_commerce': {
            'patterns': [r'ansab', r'ansab-commerce', r'ansab\.io'],
            'confidence_weight': 0.75
        }
    }

    def __init__(self):
        self.detected_platforms_cache = {}
        log.info("PlatformRouter initialized")

    def detect_platform(self, url: str, headers: Dict = None, html_content: str = None) -> Dict:
        """
        Detect platform from URL and content

        Returns:
        {
            'platform': str,
            'confidence': float (0-100),
            'processing_engine': str,
            'signals': List[str],
            'recommended_fields': List[str]
        }
        """
        log.info(f"Detecting platform for: {url}")

        # Check cache first
        cache_key = url.split('?')[0]  # Remove query params
        if cache_key in self.detected_platforms_cache:
            log.info(f"Using cached detection for {url}")
            return self.detected_platforms_cache[cache_key]

        scores = {}
        signals = []

        # Get domain info
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Score each platform
        for platform, config in self.PLATFORM_MARKERS.items():
            platform_score = 0
            platform_signals = []

            # Header matching
            if headers:
                for header_key, header_value in headers.items():
                    for marker in config.get('headers', []):
                        if marker.lower() in header_key.lower() or marker.lower() in str(header_value).lower():
                            platform_score += 20
                            platform_signals.append(f"header:{marker}")

            # URL pattern matching
            for pattern in config.get('patterns', []):
                if re.search(pattern, url, re.IGNORECASE):
                    platform_score += 15
                    platform_signals.append(f"url_pattern:{pattern[:20]}")

            # HTML content matching
            if html_content:
                for pattern in config.get('patterns', []):
                    if re.search(pattern, html_content[:10000], re.IGNORECASE):  # Check first 10KB
                        platform_score += 10
                        platform_signals.append(f"html_pattern:{pattern[:20]}")

            # Domain-based detection
            if 'shopify' in domain:
                platform_score += 30 if platform == 'shopify' else -10
            elif 'wordpress.com' in domain or 'woocommerce' in domain:
                platform_score += 30 if platform in ['wordpress', 'woocommerce'] else -10
            elif 'magento' in domain:
                platform_score += 30 if platform == 'magento' else -10
            elif 'wix' in domain:
                platform_score += 30 if platform == 'wix' else -10
            elif 'squarespace' in domain:
                platform_score += 30 if platform == 'squarespace' else -10
            elif 'ansab' in domain:
                platform_score += 30 if platform == 'ansab_commerce' else -10

            # Apply confidence weight
            final_score = platform_score * config.get('confidence_weight', 0.5)

            if final_score > 0:
                scores[platform] = {
                    'score': final_score,
                    'signals': platform_signals
                }

        # Determine best match
        if scores:
            best_platform = max(scores.items(), key=lambda x: x[1]['score'])
            platform_name = best_platform[0]
            confidence = min(99, int(best_platform[1]['score']))
            signals = best_platform[1]['signals']
        else:
            platform_name = 'generic'
            confidence = 0
            signals = ['no_markers_found']

        # Determine processing engine
        engine = self._get_processing_engine(platform_name)

        result = {
            'platform': platform_name,
            'confidence': confidence,
            'processing_engine': engine,
            'signals': signals,
            'recommended_fields': self._get_recommended_fields(platform_name),
            'url': url
        }

        # Cache result
        self.detected_platforms_cache[cache_key] = result

        log.info(f"Detected: {platform_name} ({confidence}%) - Engine: {engine}")
        return result

    def _get_processing_engine(self, platform: str) -> str:
        """Get the appropriate processing engine for detected platform"""

        engines = {
            'shopify': 'shopify_crawler',
            'woocommerce': 'woocommerce_crawler',
            'wordpress': 'wordpress_crawler',
            'magento': 'magento_crawler',
            'bigcommerce': 'bigcommerce_crawler',
            'wix': 'wix_crawler',
            'squarespace': 'squarespace_crawler',
            'custom_fabric': 'custom_fabric_processor',
            'ansab_commerce': 'ansab_commerce_processor',
            'generic': 'generic_crawler'
        }

        engine = engines.get(platform, 'generic_crawler')
        log.info(f"Engine selected: {engine} for platform: {platform}")
        return engine

    def _get_recommended_fields(self, platform: str) -> List[str]:
        """Get platform-specific recommended fields to extract"""

        fields_map = {
            'shopify': ['title', 'handle', 'product_id', 'variants', 'images', 'price', 'inventory'],
            'woocommerce': ['name', 'slug', 'id', 'variations', 'images', 'price', 'stock'],
            'wordpress': ['title', 'slug', 'post_id', 'meta_fields', 'featured_image', 'custom_price'],
            'magento': ['name', 'sku', 'entity_id', 'configurable_options', 'gallery', 'price'],
            'bigcommerce': ['name', 'sku', 'id', 'variants', 'images', 'price', 'inventory'],
            'wix': ['title', 'id', 'variants', 'images', 'price'],
            'squarespace': ['title', 'id', 'variants', 'images', 'price'],
            'custom_fabric': ['item_name', 'fabric_id', 'colors', 'sizes', 'price', 'meta'],
            'ansab_commerce': ['product_name', 'sku', 'variants', 'images', 'pricing'],
            'generic': ['title', 'price', 'description', 'image', 'url']
        }

        return fields_map.get(platform, fields_map['generic'])

    def route_to_engine(self, detection_result: Dict):
        """Route to appropriate processing engine based on detection"""

        engine = detection_result['processing_engine']
        platform = detection_result['platform']

        log.info(f"Routing to engine: {engine} for platform: {platform}")

        # Return engine configuration
        return {
            'engine': engine,
            'platform': platform,
            'confidence': detection_result['confidence'],
            'fields': detection_result['recommended_fields'],
            'special_handling': self._get_special_handling(platform)
        }

    def _get_special_handling(self, platform: str) -> Dict:
        """Get platform-specific handling instructions"""

        handling = {
            'shopify': {
                'api_available': True,
                'rate_limit': 2,
                'bulk_operations': True,
                'pagination_type': 'cursor'
            },
            'woocommerce': {
                'api_available': True,
                'rate_limit': 10,
                'bulk_operations': True,
                'pagination_type': 'offset'
            },
            'wordpress': {
                'api_available': True,
                'rate_limit': 20,
                'bulk_operations': False,
                'pagination_type': 'offset'
            },
            'magento': {
                'api_available': True,
                'rate_limit': 5,
                'bulk_operations': True,
                'pagination_type': 'cursor'
            },
            'custom_fabric': {
                'api_available': False,
                'rate_limit': 1,
                'bulk_operations': False,
                'pagination_type': 'scroll'
            },
            'ansab_commerce': {
                'api_available': False,
                'rate_limit': 2,
                'bulk_operations': False,
                'pagination_type': 'offset'
            },
            'generic': {
                'api_available': False,
                'rate_limit': 1,
                'bulk_operations': False,
                'pagination_type': 'scroll'
            }
        }

        return handling.get(platform, handling['generic'])

    def get_platform_info(self, platform: str) -> Dict:
        """Get complete platform information"""

        return {
            'platform': platform,
            'engine': self._get_processing_engine(platform),
            'fields': self._get_recommended_fields(platform),
            'handling': self._get_special_handling(platform),
            'markers': self.PLATFORM_MARKERS.get(platform, {})
        }


# Global router instance
_router = None

def get_router():
    global _router
    if _router is None:
        _router = PlatformRouter()
    return _router
