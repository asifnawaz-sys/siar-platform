"""
WordPress/WooCommerce Scraper
Professional wrapper for Ayesha Somaya WordPress scraper
Handles WordPress and WooCommerce platforms
"""

import logging
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin, urlparse

log = logging.getLogger('siar.scrapers.wordpress')

class WordPressScraper:
    """Scraper for WordPress/WooCommerce platforms"""

    # WooCommerce and WordPress indicators
    WORDPRESS_INDICATORS = [
        'wp-content', 'wp-includes', 'wp-admin', '/wp-json/',
        'wordpress', 'woocommerce', 'woo-', 'add-to-cart'
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.visited_urls = set()
        log.info("WordPressScraper initialized")

    def scrape(self, url: str, limit: int = 250) -> List[Dict]:
        """
        Scrape products from WordPress/WooCommerce site

        Args:
            url: WordPress site URL
            limit: Maximum products to extract

        Returns:
            List of product dictionaries
        """
        log.info(f"Starting WordPress scrape of {url} (limit: {limit})")

        products = []

        try:
            # Try WooCommerce REST API first
            products = self._try_woocommerce_api(url, limit)
            if products:
                log.info(f"Used WooCommerce API: {len(products)} products")
                return products[:limit]
        except Exception as e:
            log.debug(f"WooCommerce API failed: {e}")

        # Fall back to HTML scraping
        try:
            products = self._scrape_html(url, limit)
            log.info(f"Used HTML scraping: {len(products)} products")
        except Exception as e:
            log.error(f"HTML scraping failed: {e}")

        return products[:limit]

    def _try_woocommerce_api(self, url: str, limit: int) -> List[Dict]:
        """Try to use WooCommerce REST API"""
        base_url = self._get_base_url(url)

        # Common WooCommerce API endpoints
        api_endpoints = [
            f"{base_url}/wp-json/wc/v3/products",
            f"{base_url}/wp-json/wc/v2/products",
            f"{base_url}/wp-json/wc/v1/products"
        ]

        for endpoint in api_endpoints:
            try:
                response = self.session.get(
                    endpoint,
                    params={'per_page': min(limit, 100)},
                    timeout=10
                )

                if response.status_code == 200:
                    products = response.json()
                    if isinstance(products, list):
                        log.info(f"✓ WooCommerce API available at {endpoint}")
                        return self._normalize_woo_products(products)
            except:
                continue

        raise Exception("WooCommerce API not available")

    def _normalize_woo_products(self, products: List) -> List[Dict]:
        """Normalize WooCommerce API products"""
        normalized = []

        for p in products:
            try:
                images = p.get('images', [])
                image_url = images[0]['src'] if images else ""

                product = {
                    'title': p.get('name', ''),
                    'handle': p.get('slug', ''),
                    'url': p.get('permalink', ''),
                    'price': str(p.get('price', '')),
                    'image': image_url,
                    'description': p.get('description', ''),
                    'sku': p.get('sku', ''),
                    'stock': p.get('stock_quantity'),
                    'platform': 'wordpress'
                }

                # Handle variations/variants
                if 'variations' in p:
                    product['variants'] = p['variations']

                normalized.append(product)
            except Exception as e:
                log.debug(f"Error normalizing product: {e}")
                continue

        return normalized

    def _scrape_html(self, url: str, limit: int) -> List[Dict]:
        """Scrape products from HTML"""
        products = []
        base_url = self._get_base_url(url)

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find product items (common WooCommerce selectors)
            product_selectors = [
                '.product',
                '.product-item',
                'li[data-product-id]',
                'article.type-product'
            ]

            product_items = []
            for selector in product_selectors:
                product_items.extend(soup.select(selector)[:limit])

            log.info(f"Found {len(product_items)} product items")

            for item in product_items:
                if len(products) >= limit:
                    break

                try:
                    product = self._extract_product_html(item, base_url)
                    if product:
                        products.append(product)
                except Exception as e:
                    log.debug(f"Error extracting product: {e}")
                    continue

            return products

        except Exception as e:
            log.error(f"Error scraping HTML: {e}")
            return products

    def _extract_product_html(self, item, base_url: str) -> Optional[Dict]:
        """Extract product from HTML element"""

        # Title
        title_elem = item.select_one('h2, h3, .product-title, .woocommerce-loop-product__title')
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        handle = self._slugify(title)

        # Link
        link_elem = item.select_one('a')
        if not link_elem or 'href' not in link_elem.attrs:
            return None

        product_url = link_elem['href']
        if not product_url.startswith('http'):
            product_url = urljoin(base_url, product_url)

        # Price
        price_elem = item.select_one('.price, .woocommerce-Price-amount, .product-price')
        price = price_elem.get_text(strip=True) if price_elem else ""

        # Image
        img_elem = item.select_one('img')
        image_url = img_elem.get('src', '') if img_elem else ""

        # Description
        desc_elem = item.select_one('.description, .product-short-description')
        description = desc_elem.get_text(strip=True) if desc_elem else ""

        return {
            'title': title,
            'handle': handle,
            'url': product_url,
            'price': price,
            'image': image_url,
            'description': description,
            'platform': 'wordpress'
        }

    def _get_base_url(self, url: str) -> str:
        """Extract base URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _slugify(self, text: str) -> str:
        """Convert to URL-friendly slug"""
        text = str(text).lower()
        text = re.sub(r'[^\w\s\-]', '', text)
        text = re.sub(r'[\s_]+', '-', text)
        return text.strip('-')

    def close(self):
        """Clean up session"""
        self.session.close()
        log.info("WordPressScraper closed")
