"""
Universal scraper service supporting all major e-commerce platforms.
Routes to platform-specific crawlers or generic fallback.
"""

import logging
from typing import List, Dict, Tuple, Any

from .platform_detector import PlatformDetector, detect_platform
from .crawlers import ShopifyCrawler, WooCommerceCrawler, MagentoCrawler, GenericCrawler
from .shopify import export_shopify_csv

log = logging.getLogger("siar.scraper")


class ScraperService:
    """Main scraping orchestrator supporting all platforms."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.detector = PlatformDetector(timeout=timeout)
        self.crawlers = {
            "shopify": ShopifyCrawler(timeout=timeout),
            "woocommerce": WooCommerceCrawler(timeout=timeout),
            "magento": MagentoCrawler(timeout=timeout),
            "generic": GenericCrawler(timeout=timeout),
        }

    def scrape(self, url: str, limit: int = 250) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Detect platform and scrape products.

        Returns:
            (detection_result, products_list)
        """
        try:
            # Detect platform
            detected = self.detector.detect(url)
            log.info(f"Platform detected: {detected['platform']} ({detected['confidence']}%)")

            # Route to appropriate crawler
            platform = detected.get("platform", "generic")
            crawler = self.crawlers.get(platform, self.crawlers["generic"])

            # Scrape products
            products = crawler.scrape(url, limit=limit)
            log.info(f"Scraped {len(products)} products from {platform}")

            return detected, products

        except Exception as e:
            log.error(f"Scrape failed: {e}", exc_info=True)
            raise

    def export_shopify(self, products: List[Dict[str, Any]], output_path: str) -> str:
        """Export products to Shopify CSV format."""
        try:
            path = export_shopify_csv(products, output_path)
            log.info(f"Exported {len(products)} products to {path}")
            return str(path)
        except Exception as e:
            log.error(f"Export failed: {e}", exc_info=True)
            raise
