"""
Ansab Commerce Platform Scraper
Professional wrapper for Ansab Jahangir Studio custom platform
"""

import logging
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import re
import time

log = logging.getLogger('siar.scrapers.ansab_commerce')

class AnsabCommerceScraper:
    """Scraper for Ansab Jahangir custom commerce platform"""

    # Ansab-specific collections (pre-configured)
    DEFAULT_COLLECTIONS = [
        "https://www.ansabjahangirstudio.com/ready-to-ship",
        "https://www.ansabjahangirstudio.com/the-velvet-dynasty-drop-ii",
        "https://www.ansabjahangirstudio.com/so-hot-luxury-velvets",
        "https://www.ansabjahangirstudio.com/marigold-and-gota-2",
        "https://www.ansabjahangirstudio.com/luxe-pret-2",
        "https://www.ansabjahangirstudio.com/digital-silk",
        "https://www.ansabjahangirstudio.com/signature-4",
        "https://www.ansabjahangirstudio.com/velvets",
        "https://www.ansabjahangirstudio.com/formals",
        "https://www.ansabjahangirstudio.com/bridals",
        "https://www.ansabjahangirstudio.com/sale",
        "https://www.ansabjahangirstudio.com/kids-festive",
        "https://www.ansabjahangirstudio.com/menswear",
        "https://www.ansabjahangirstudio.com/celebrity-spotted",
        "https://www.ansabjahangirstudio.com/basics"
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        log.info("AnsabCommerceScraper initialized")

    def scrape(self, url: str = None, limit: int = 250) -> List[Dict]:
        """
        Scrape Ansab products

        Args:
            url: Optional collection URL (if None, uses all default collections)
            limit: Maximum products to extract

        Returns:
            List of product dictionaries
        """
        log.info(f"Starting Ansab scrape (limit: {limit})")

        products = []
        urls_to_scrape = [url] if url else self.DEFAULT_COLLECTIONS

        for collection_url in urls_to_scrape:
            if len(products) >= limit:
                break

            try:
                log.info(f"Scraping collection: {collection_url}")
                collection_products = self._scrape_collection(collection_url, limit - len(products))
                products.extend(collection_products)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                log.warning(f"Failed to scrape {collection_url}: {e}")
                continue

        log.info(f"Scraped {len(products)} products from Ansab")
        return products[:limit]

    def _scrape_collection(self, url: str, limit: int) -> List[Dict]:
        """Scrape single collection"""
        products = []

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all product items
            product_items = soup.find_all('div', class_='product-item')

            for item in product_items:
                if len(products) >= limit:
                    break

                try:
                    product = self._extract_product_details(item, url)
                    if product:
                        products.append(product)
                except Exception as e:
                    log.debug(f"Failed to extract product: {e}")
                    continue

            return products

        except Exception as e:
            log.error(f"Error scraping collection {url}: {e}")
            return products

    def _extract_product_details(self, item, collection_url: str) -> Dict:
        """Extract details from single product item"""

        # Title
        title_tag = item.find('h2', class_='product-title')
        if not title_tag:
            return None

        title = title_tag.text.strip()
        handle = re.sub(r'[^\w\-]', '-', title.lower()).strip('-')

        # Product link
        link_tag = item.find('a')
        if not link_tag or 'href' not in link_tag.attrs:
            return None

        product_url = link_tag['href']
        if not product_url.startswith('http'):
            product_url = "https://www.ansabjahangirstudio.com" + product_url

        # Price
        price_tag = item.find('span', class_='price')
        price = price_tag.text.strip() if price_tag else ""

        # Image
        img_tag = item.find('img')
        image_url = img_tag.get('src', '') if img_tag else ""

        # Description
        desc_tag = item.find('div', class_='product-description')
        description = desc_tag.text.strip() if desc_tag else ""

        return {
            'title': title,
            'handle': handle,
            'url': product_url,
            'price': price,
            'image': image_url,
            'description': description,
            'collection': collection_url.split('/')[-1],
            'platform': 'ansab_commerce',
            'sku': handle
        }

    def close(self):
        """Clean up session"""
        self.session.close()
        log.info("AnsabCommerceScraper closed")
