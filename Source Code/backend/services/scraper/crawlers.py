"""
Platform-specific crawlers for Shopify, WooCommerce, Magento, and other e-commerce platforms.
Each crawler extracts product data using platform-specific APIs and DOM extraction.
"""

import logging
import requests
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import json
import re

logger = logging.getLogger("siar.crawlers")

class BaseCrawler:
    """Abstract base for all platform crawlers."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a browser-like session."""
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return s

    def normalize_url(self, url: str) -> str:
        """Ensure URL has protocol."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url.rstrip("/")

    def safe_handle(self, value: str) -> str:
        """Generate safe URL handle from text."""
        if not value:
            return "product"
        value = re.sub(r"<[^>]+>", "", str(value))
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
        return value[:255] or "product"

    def scrape(self, url: str, limit: int = 250) -> List[Dict[str, Any]]:
        """Override in subclass."""
        raise NotImplementedError


class ShopifyCrawler(BaseCrawler):
    """Shopify-specific crawler using products.json API."""

    def scrape(self, url: str, limit: int = 250) -> List[Dict[str, Any]]:
        """Fetch products from Shopify's products.json endpoint."""
        url = self.normalize_url(url)

        # Build endpoint
        endpoint = f"{url}/products.json?limit={min(max(int(limit), 1), 250)}"

        try:
            r = self.session.get(endpoint, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()

            if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                raise ValueError("Invalid Shopify products.json response")

            products = []
            for raw in data["products"]:
                handle = self.safe_handle(raw.get("handle") or raw.get("title"))
                variants = []

                for rv in raw.get("variants") or [{}]:
                    inv = rv.get("inventory_quantity")
                    variants.append({
                        "sku": rv.get("sku") or "",
                        "title": rv.get("title") or "",
                        "option1": rv.get("option1") or "",
                        "option2": rv.get("option2") or "",
                        "option3": rv.get("option3") or "",
                        "price": str(rv.get("price") or ""),
                        "compare_at_price": str(rv.get("compare_at_price") or ""),
                        "barcode": rv.get("barcode") or "",
                        "weight_grams": rv.get("grams"),
                        "weight_unit": "g",
                        "inventory_quantity": inv if isinstance(inv, int) else None,
                        "inventory_policy": "continue" if rv.get("inventory_policy") == "continue" else "deny",
                        "inventory_tracker": "shopify" if inv is not None else "",
                        "image_src": "",
                        "taxable": True,
                        "requires_shipping": True,
                    })

                products.append({
                    "handle": handle,
                    "title": raw.get("title") or "",
                    "body_html": raw.get("body_html") or "",
                    "vendor": raw.get("vendor") or "",
                    "product_type": raw.get("product_type") or "",
                    "category": "",
                    "tags": ", ".join(raw.get("tags") or []) if isinstance(raw.get("tags"), list) else raw.get("tags", ""),
                    "published": True,
                    "status": "active",
                    "images": [{"src": x.get("src", ""), "alt": x.get("alt", "")} for x in (raw.get("images") or []) if x.get("src")],
                    "variants": variants,
                    "source_url": f"{url}/products/{handle}",
                    "platform": "shopify",
                })

            return products
        except Exception as e:
            logger.error(f"Shopify scrape failed: {e}")
            raise


class WooCommerceCrawler(BaseCrawler):
    """WooCommerce crawler using REST API and DOM extraction."""

    def scrape(self, url: str, limit: int = 250) -> List[Dict[str, Any]]:
        """Fetch WooCommerce products via REST API."""
        url = self.normalize_url(url)

        try:
            # Try REST API first
            endpoint = f"{url}/wp-json/wc/v3/products?per_page={min(limit, 100)}"

            r = self.session.get(endpoint, timeout=self.timeout)

            if r.status_code == 200:
                return self._parse_woo_api(r.json(), url)
            else:
                # Fallback to DOM extraction
                return self._parse_woo_html(url, limit)
        except Exception as e:
            logger.error(f"WooCommerce scrape failed: {e}")
            try:
                return self._parse_woo_html(url, limit)
            except Exception as e2:
                logger.error(f"WooCommerce HTML fallback failed: {e2}")
                raise

    def _parse_woo_api(self, data: List[Dict], base_url: str) -> List[Dict[str, Any]]:
        """Parse WooCommerce REST API response."""
        products = []

        for item in data:
            handle = self.safe_handle(item.get("slug") or item.get("name"))
            variants = []

            if item.get("variations"):
                # Product has variations
                for var_id in item.get("variations", [])[:50]:
                    variants.append({
                        "sku": item.get("sku") or "",
                        "title": item.get("name") or "",
                        "option1": "",
                        "option2": "",
                        "option3": "",
                        "price": str(item.get("price") or ""),
                        "compare_at_price": str(item.get("regular_price") or ""),
                        "barcode": "",
                        "weight_grams": None,
                        "weight_unit": "g",
                        "inventory_quantity": item.get("stock_quantity"),
                        "inventory_policy": "deny" if not item.get("manage_stock") else "continue",
                        "inventory_tracker": "woocommerce" if item.get("stock_quantity") is not None else "",
                        "image_src": "",
                        "taxable": item.get("tax_status") == "taxable",
                        "requires_shipping": item.get("shipping_required", True),
                    })
            else:
                # Single product
                variants.append({
                    "sku": item.get("sku") or "",
                    "title": item.get("name") or "",
                    "option1": "",
                    "option2": "",
                    "option3": "",
                    "price": str(item.get("price") or ""),
                    "compare_at_price": str(item.get("regular_price") or ""),
                    "barcode": "",
                    "weight_grams": None,
                    "weight_unit": "g",
                    "inventory_quantity": item.get("stock_quantity"),
                    "inventory_policy": "deny" if not item.get("manage_stock") else "continue",
                    "inventory_tracker": "woocommerce" if item.get("stock_quantity") is not None else "",
                    "image_src": "",
                    "taxable": item.get("tax_status") == "taxable",
                    "requires_shipping": item.get("shipping_required", True),
                })

            images = []
            if item.get("images"):
                for img in item["images"]:
                    images.append({"src": img.get("src", ""), "alt": img.get("alt", "")})

            products.append({
                "handle": handle,
                "title": item.get("name") or "",
                "body_html": item.get("description") or "",
                "vendor": "",
                "product_type": ",".join([c.get("name", "") for c in item.get("categories", [])]),
                "category": ",".join([c.get("name", "") for c in item.get("categories", [])]),
                "tags": ",".join([t.get("name", "") for t in item.get("tags", [])]),
                "published": item.get("status") == "publish",
                "status": item.get("status") or "draft",
                "images": images,
                "variants": variants,
                "source_url": item.get("permalink") or f"{base_url}/product/{handle}",
                "platform": "woocommerce",
            })

        return products

    def _parse_woo_html(self, url: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback: Parse WooCommerce from HTML when API unavailable."""
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        products = []
        product_elements = soup.find_all("li", class_=re.compile("product"))[:limit]

        for elem in product_elements:
            try:
                title_elem = elem.find("h2", class_=re.compile("title")) or elem.find("a")
                title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                handle = self.safe_handle(title)

                price_elem = elem.find(class_=re.compile("price"))
                price = price_elem.get_text(strip=True) if price_elem else ""

                images = []
                img_elem = elem.find("img")
                if img_elem:
                    src = img_elem.get("src") or img_elem.get("data-src")
                    images.append({"src": urljoin(url, src), "alt": img_elem.get("alt", "")})

                products.append({
                    "handle": handle,
                    "title": title,
                    "body_html": "",
                    "vendor": "",
                    "product_type": "",
                    "category": "",
                    "tags": "",
                    "published": True,
                    "status": "active",
                    "images": images,
                    "variants": [{
                        "sku": "",
                        "title": title,
                        "option1": "",
                        "option2": "",
                        "option3": "",
                        "price": price,
                        "compare_at_price": "",
                        "barcode": "",
                        "weight_grams": None,
                        "weight_unit": "g",
                        "inventory_quantity": None,
                        "inventory_policy": "deny",
                        "inventory_tracker": "",
                        "image_src": "",
                        "taxable": True,
                        "requires_shipping": True,
                    }],
                    "source_url": urljoin(url, title_elem.get("href")) if title_elem else url,
                    "platform": "woocommerce",
                })
            except Exception as e:
                logger.warning(f"Failed to parse WooCommerce product: {e}")
                continue

        return products


class MagentoCrawler(BaseCrawler):
    """Magento 1 & 2 crawler."""

    def scrape(self, url: str, limit: int = 250) -> List[Dict[str, Any]]:
        """Fetch Magento products."""
        url = self.normalize_url(url)

        try:
            # Try Magento 2 REST API
            endpoint = f"{url}/rest/V1/products"
            r = self.session.get(endpoint, timeout=self.timeout)

            if r.status_code == 200:
                data = r.json()
                return self._parse_magento_api(data.get("items", [])[:limit], url)
            else:
                return self._parse_magento_html(url, limit)
        except Exception as e:
            logger.error(f"Magento scrape failed: {e}")
            try:
                return self._parse_magento_html(url, limit)
            except Exception as e2:
                logger.error(f"Magento HTML fallback failed: {e2}")
                raise

    def _parse_magento_api(self, data: List[Dict], base_url: str) -> List[Dict[str, Any]]:
        """Parse Magento REST API response."""
        products = []

        for item in data:
            handle = self.safe_handle(item.get("sku") or item.get("name"))
            variants = []

            variants.append({
                "sku": item.get("sku") or "",
                "title": item.get("name") or "",
                "option1": "",
                "option2": "",
                "option3": "",
                "price": str(item.get("price") or ""),
                "compare_at_price": "",
                "barcode": "",
                "weight_grams": None,
                "weight_unit": "g",
                "inventory_quantity": None,
                "inventory_policy": "deny",
                "inventory_tracker": "",
                "image_src": "",
                "taxable": True,
                "requires_shipping": True,
            })

            images = []
            if item.get("media_gallery_entries"):
                for img in item["media_gallery_entries"][:50]:
                    images.append({
                        "src": urljoin(base_url, img.get("file", "")),
                        "alt": img.get("label", "")
                    })

            products.append({
                "handle": handle,
                "title": item.get("name") or "",
                "body_html": item.get("description") or "",
                "vendor": "",
                "product_type": ",".join(item.get("type_id", [])) if isinstance(item.get("type_id"), list) else item.get("type_id", ""),
                "category": ",".join(item.get("custom_attributes", {}).get("category_ids", [])) if isinstance(item.get("custom_attributes", {}).get("category_ids"), list) else "",
                "tags": "",
                "published": item.get("status") == 1,
                "status": "active" if item.get("status") == 1 else "inactive",
                "images": images,
                "variants": variants,
                "source_url": item.get("url_key") or f"{base_url}/products/{handle}",
                "platform": "magento",
            })

        return products

    def _parse_magento_html(self, url: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback: Parse Magento from HTML."""
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        products = []
        product_elements = soup.find_all(class_=re.compile("product"))[:limit]

        for elem in product_elements:
            try:
                title = elem.find(class_="product-name") or elem.find("h2")
                title_text = title.get_text(strip=True) if title else "Unknown"
                handle = self.safe_handle(title_text)

                price = elem.find(class_=re.compile("price"))
                price_text = price.get_text(strip=True) if price else ""

                images = []
                img = elem.find("img")
                if img:
                    images.append({"src": urljoin(url, img.get("src", "")), "alt": img.get("alt", "")})

                products.append({
                    "handle": handle,
                    "title": title_text,
                    "body_html": "",
                    "vendor": "",
                    "product_type": "",
                    "category": "",
                    "tags": "",
                    "published": True,
                    "status": "active",
                    "images": images,
                    "variants": [{
                        "sku": "",
                        "title": title_text,
                        "option1": "",
                        "option2": "",
                        "option3": "",
                        "price": price_text,
                        "compare_at_price": "",
                        "barcode": "",
                        "weight_grams": None,
                        "weight_unit": "g",
                        "inventory_quantity": None,
                        "inventory_policy": "deny",
                        "inventory_tracker": "",
                        "image_src": "",
                        "taxable": True,
                        "requires_shipping": True,
                    }],
                    "source_url": urljoin(url, title.get("href")) if title and title.get("href") else url,
                    "platform": "magento",
                })
            except Exception as e:
                logger.warning(f"Failed to parse Magento product: {e}")
                continue

        return products


class GenericCrawler(BaseCrawler):
    """Generic fallback crawler for unknown platforms."""

    def scrape(self, url: str, limit: int = 250) -> List[Dict[str, Any]]:
        """Parse any website generically."""
        url = self.normalize_url(url)

        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")

            products = []

            # Try to find product elements
            product_selectors = [
                "article.product",
                "div.product",
                "li.product",
                "div[data-product]",
                "div[itemtype*='Product']",
            ]

            product_elements = []
            for selector in product_selectors:
                elements = soup.select(selector)
                if elements:
                    product_elements = elements[:limit]
                    break

            if not product_elements:
                # No products found, return single product from page
                title = soup.title.get_text(strip=True) if soup.title else "Product"
                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text(strip=True)

                images = []
                for img in soup.find_all("img")[:50]:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        images.append({"src": urljoin(url, src), "alt": img.get("alt", "")})

                handle = self.safe_handle(title)
                return [{
                    "handle": handle,
                    "title": title,
                    "body_html": "",
                    "vendor": "",
                    "product_type": "",
                    "category": "",
                    "tags": "",
                    "published": True,
                    "status": "active",
                    "images": images,
                    "variants": [{
                        "sku": "",
                        "title": title,
                        "option1": "",
                        "option2": "",
                        "option3": "",
                        "price": "",
                        "compare_at_price": "",
                        "barcode": "",
                        "weight_grams": None,
                        "weight_unit": "g",
                        "inventory_quantity": None,
                        "inventory_policy": "deny",
                        "inventory_tracker": "",
                        "image_src": "",
                        "taxable": True,
                        "requires_shipping": True,
                    }],
                    "source_url": url,
                    "platform": "generic",
                }]

            for elem in product_elements:
                try:
                    # Find title
                    title_elem = elem.find(["h2", "h3", "a"])
                    title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                    handle = self.safe_handle(title)

                    # Find price
                    price_elem = elem.find(class_=re.compile("price"))
                    price = price_elem.get_text(strip=True) if price_elem else ""

                    # Find images
                    images = []
                    for img in elem.find_all("img")[:10]:
                        src = img.get("src") or img.get("data-src")
                        if src:
                            images.append({"src": urljoin(url, src), "alt": img.get("alt", "")})

                    products.append({
                        "handle": handle,
                        "title": title,
                        "body_html": "",
                        "vendor": "",
                        "product_type": "",
                        "category": "",
                        "tags": "",
                        "published": True,
                        "status": "active",
                        "images": images,
                        "variants": [{
                            "sku": "",
                            "title": title,
                            "option1": "",
                            "option2": "",
                            "option3": "",
                            "price": price,
                            "compare_at_price": "",
                            "barcode": "",
                            "weight_grams": None,
                            "weight_unit": "g",
                            "inventory_quantity": None,
                            "inventory_policy": "deny",
                            "inventory_tracker": "",
                            "image_src": "",
                            "taxable": True,
                            "requires_shipping": True,
                        }],
                        "source_url": urljoin(url, title_elem.get("href")) if title_elem and title_elem.get("href") else url,
                        "platform": "generic",
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse generic product: {e}")
                    continue

            return products if products else []

        except Exception as e:
            logger.error(f"Generic scrape failed: {e}")
            raise
