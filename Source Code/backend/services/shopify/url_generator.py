"""
Shopify URL Generator
Generate Shopify URLs from image names and product data
"""

import logging
from typing import List, Dict
import re

log = logging.getLogger('siar.shopify_url_generator')

class ShopifyURLGenerator:
    """Generate Shopify URLs from image names and product titles"""

    def __init__(self, shop_domain: str = None):
        self.shop_domain = shop_domain or "myshop.myshopify.com"
        log.info(f"ShopifyURLGenerator initialized for {self.shop_domain}")

    def generate_from_image_name(self, image_name: str) -> Dict:
        """
        Generate Shopify URL from image name

        Args:
            image_name: Image file name (e.g., "product-sku-001.jpg")

        Returns:
            {
                'source': image_name,
                'url': 'https://myshop.myshopify.com/products/product-sku-001',
                'product_handle': 'product-sku-001'
            }
        """
        # Remove extension
        name_without_ext = re.sub(r'\.\w+$', '', image_name)

        # Clean up handle
        handle = self._clean_handle(name_without_ext)

        url = f"https://{self.shop_domain}/products/{handle}"

        return {
            'source': image_name,
            'url': url,
            'product_handle': handle
        }

    def generate_from_product_name(self, product_name: str, collection: str = None) -> Dict:
        """
        Generate Shopify URL from product name

        Args:
            product_name: Product name/title
            collection: Optional collection slug

        Returns:
            URL information
        """
        handle = self._clean_handle(product_name)

        if collection:
            collection_handle = self._clean_handle(collection)
            url = f"https://{self.shop_domain}/collections/{collection_handle}/products/{handle}"
        else:
            url = f"https://{self.shop_domain}/products/{handle}"

        return {
            'source': product_name,
            'url': url,
            'product_handle': handle,
            'collection': collection
        }

    def batch_generate(self, items: List[Dict]) -> List[Dict]:
        """
        Generate URLs for multiple items

        Args:
            items: List of dictionaries with 'name' and optional 'collection'

        Returns:
            List of URL information
        """
        results = []
        for item in items:
            name = item.get('name') or item.get('title') or item.get('image_name')
            if not name:
                continue

            collection = item.get('collection')
            result = self.generate_from_product_name(name, collection)
            results.append(result)

        log.info(f"Generated {len(results)} Shopify URLs")
        return results

    def generate_variant_urls(self, product_handle: str, variants: List[str]) -> List[Dict]:
        """
        Generate Shopify variant URLs

        Args:
            product_handle: Product URL handle
            variants: List of variant names (e.g., ["Red", "Blue", "Green"])

        Returns:
            List of variant URLs
        """
        results = []

        for variant in variants:
            variant_handle = self._clean_handle(variant)
            url = f"https://{self.shop_domain}/products/{product_handle}?variant={variant_handle}"

            results.append({
                'variant': variant,
                'handle': variant_handle,
                'url': url
            })

        return results

    def _clean_handle(self, text: str) -> str:
        """
        Convert text to Shopify-compatible handle format

        Rules:
        - Lowercase
        - Replace spaces with hyphens
        - Remove special characters
        - Remove consecutive hyphens
        - Max 255 characters
        """
        # Lowercase
        handle = text.lower()

        # Remove special characters except hyphens
        handle = re.sub(r'[^\w\s\-]', '', handle)

        # Replace spaces and underscores with hyphens
        handle = re.sub(r'[\s_]+', '-', handle)

        # Remove consecutive hyphens
        handle = re.sub(r'-+', '-', handle)

        # Remove leading/trailing hyphens
        handle = handle.strip('-')

        # Limit length
        handle = handle[:255]

        return handle

    def set_shop_domain(self, domain: str):
        """Set Shopify shop domain"""
        self.shop_domain = domain
        log.info(f"Shop domain updated to: {domain}")

    def validate_handle(self, handle: str) -> bool:
        """Validate Shopify handle format"""
        # Shopify handle rules
        if not handle:
            return False
        if len(handle) > 255:
            return False
        if not re.match(r'^[a-z0-9\-]+$', handle):
            return False
        return True
