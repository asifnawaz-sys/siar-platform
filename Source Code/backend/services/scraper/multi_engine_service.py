"""
Multi-Engine Scraper Service
Manages multiple specialized scrapers with automatic platform detection
Integrates custom scrapers and switches engines automatically

Supported Engines:
- Shopify (official API)
- WooCommerce (REST API)
- WordPress (custom processor)
- Magento (API v2)
- Custom Fabric Scraper
- Ansab Commerce Scraper
- Generic Fallback
"""

import logging
from typing import Dict, List, Tuple, Optional
from .platform_router import get_router
from .crawlers import (
    ShopifyCrawler, WooCommerceCrawler, MagentoCrawler, GenericCrawler
)

log = logging.getLogger('siar.multi_engine_scraper')

class MultiEngineScraperService:
    """Service that routes to appropriate scraper engine"""

    def __init__(self):
        self.router = get_router()
        self.engines = {}
        self.custom_scrapers = {}
        self._initialize_engines()
        log.info("MultiEngineScraperService initialized")

    def _initialize_engines(self):
        """Initialize all built-in scraper engines"""

        # Import custom scrapers
        try:
            from .engines.ansab_commerce import AnsabCommerceScraper
            ansab = AnsabCommerceScraper()
            log.info("✓ Ansab Commerce scraper loaded")
        except Exception as e:
            log.warning(f"Could not load Ansab scraper: {e}")
            ansab = None

        try:
            from .engines.wordpress import WordPressScraper
            wordpress = WordPressScraper()
            log.info("✓ WordPress scraper loaded")
        except Exception as e:
            log.warning(f"Could not load WordPress scraper: {e}")
            wordpress = None

        self.engines = {
            'shopify_crawler': ShopifyCrawler(),
            'woocommerce_crawler': WooCommerceCrawler(),
            'magento_crawler': MagentoCrawler(),
            'generic_crawler': GenericCrawler(),
            'wordpress_crawler': wordpress,
            'custom_fabric_processor': None,
            'ansab_commerce_processor': ansab,
            'bigcommerce_crawler': None,
            'wix_crawler': None,
            'squarespace_crawler': None,
        }

        log.info("Engines initialized")

    def register_custom_scraper(self, engine_name: str, scraper_class) -> bool:
        """
        Register a custom scraper engine

        Args:
            engine_name: Unique engine identifier (e.g., 'custom_fabric_processor')
            scraper_class: Instantiated scraper class with scrape() method

        Returns:
            bool: Registration success
        """
        try:
            self.custom_scrapers[engine_name] = scraper_class
            self.engines[engine_name] = scraper_class
            log.info(f"Registered custom scraper: {engine_name}")
            return True
        except Exception as e:
            log.error(f"Failed to register scraper {engine_name}: {e}")
            return False

    def scrape(self, url: str, limit: int = 250,
               headers: Dict = None, html_content: str = None) -> Tuple[Dict, List]:
        """
        Auto-detect platform and scrape with appropriate engine

        Process:
        1. Detect platform using router
        2. Get recommended processing engine
        3. Route to specialized scraper
        4. Return detected platform info + products
        """

        log.info(f"Starting auto-detection scrape for: {url}")

        # Step 1: Detect platform
        detection = self.router.detect_platform(url, headers, html_content)
        log.info(f"Platform detected: {detection['platform']} "
                f"(confidence: {detection['confidence']}%)")

        # Step 2: Get appropriate engine
        engine_name = detection['processing_engine']
        engine = self.engines.get(engine_name)

        if not engine:
            log.warning(f"Engine {engine_name} not available, falling back to generic")
            engine = self.engines['generic_crawler']
            engine_name = 'generic_crawler'

        # Step 3: Route to engine
        routing_info = self.router.route_to_engine(detection)
        log.info(f"Using engine: {engine_name} with {len(routing_info['fields'])} fields")

        # Step 4: Perform scraping
        try:
            products = engine.scrape(url, limit=limit)
            log.info(f"Scraped {len(products)} products using {engine_name}")

            return {
                'detected': {
                    'platform': detection['platform'],
                    'confidence': detection['confidence'],
                    'engine': engine_name,
                    'signals': detection['signals'],
                    'fields': routing_info['fields']
                }
            }, products

        except Exception as e:
            log.error(f"Scraping failed with {engine_name}: {e}")
            # Try fallback
            if engine_name != 'generic_crawler':
                log.info("Falling back to generic crawler")
                products = self.engines['generic_crawler'].scrape(url, limit=limit)
                return {
                    'detected': {
                        'platform': 'generic',
                        'confidence': 0,
                        'engine': 'generic_crawler',
                        'error': str(e),
                        'fallback': True
                    }
                }, products
            raise

    def get_platform_details(self, url: str) -> Dict:
        """Get detailed platform information"""
        detection = self.router.detect_platform(url)
        return self.router.get_platform_info(detection['platform'])

    def supports_platform(self, platform: str) -> bool:
        """Check if platform has a dedicated scraper"""
        engine = self.router._get_processing_engine(platform)
        return self.engines.get(engine) is not None

    def list_supported_platforms(self) -> List[str]:
        """List all supported platforms"""
        return [
            'shopify', 'woocommerce', 'wordpress', 'magento',
            'bigcommerce', 'wix', 'squarespace', 'custom_fabric',
            'ansab_commerce', 'generic'
        ]

    def export_shopify(self, products: List, output_path: str):
        """Use Shopify crawler's export method"""
        crawler = self.engines['shopify_crawler']
        if crawler:
            return crawler.export_shopify(products, output_path)
        raise RuntimeError("Shopify crawler not available")


# Global instance
_service = None

def get_multi_engine_service():
    global _service
    if _service is None:
        _service = MultiEngineScraperService()
    return _service
