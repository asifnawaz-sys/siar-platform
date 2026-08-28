"""
Intelligent platform detection using confidence scoring.
Never falsely classifies HTTP errors as platform indicators.
"""

import logging
import requests
from typing import Dict

logger = logging.getLogger("siar.detector")


class PlatformDetector:
    """Detect e-commerce platform with confidence scoring."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def detect(self, url: str) -> Dict:
        """
        Return platform + confidence.

        Confidence levels:
        - 99: Definite match (API endpoint returns valid data)
        - 95: Very likely (platform headers/markers found)
        - 85: Likely (platform-specific HTML signatures)
        - 70: Possible (HTML contains platform keywords)
        - 0: Unknown (generic fallback)

        NEVER classify HTTP errors (401, 403, 404) as platform proof.
        """

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        url = url.rstrip("/")

        result = {
            "platform": "generic",
            "confidence": 0,
            "signals": [],
            "url": url
        }

        try:
            r = requests.get(url, timeout=self.timeout, allow_redirects=True, headers={
                "User-Agent": "SIAR-Digital-Platform/1.0"
            })

            if "x-sorting-hat-podid" in {k.lower(): v.lower() for k, v in r.headers.items()}:
                result["signals"].append("Shopify header (x-sorting-hat-podid)")
                result["platform"], result["confidence"] = "shopify", 95
                return result

            shopify_check = self._check_shopify_api(url)
            if shopify_check["confidence"] >= 95:
                return shopify_check

            woo_check = self._check_woocommerce(r.text, url)
            if woo_check["confidence"] >= 85:
                return woo_check

            magento_check = self._check_magento(r.text, url)
            if magento_check["confidence"] >= 85:
                return magento_check

            bigcommerce_check = self._check_bigcommerce(r.text, url)
            if bigcommerce_check["confidence"] >= 85:
                return bigcommerce_check

            wix_check = self._check_wix(r.text)
            if wix_check["confidence"] >= 85:
                return wix_check

            squarespace_check = self._check_squarespace(r.text)
            if squarespace_check["confidence"] >= 85:
                return squarespace_check

            result["confidence"] = 50 if r.status_code == 200 else 10
            result["signals"].append(f"HTTP {r.status_code}")
            return result

        except requests.RequestException as e:
            result["signals"].append(f"Request failed: {type(e).__name__}")
            return result

    def _check_shopify_api(self, url: str) -> Dict:
        """Check if /products.json returns valid Shopify data."""
        result = {"platform": "generic", "confidence": 0, "signals": [], "url": url}

        try:
            endpoint = f"{url}/products.json?limit=1"
            r = requests.get(endpoint, timeout=self.timeout, headers={
                "User-Agent": "SIAR-Digital-Platform/1.0",
                "Accept": "application/json",
            })

            if r.status_code == 200:
                try:
                    payload = r.json()
                    if isinstance(payload, dict) and isinstance(payload.get("products"), list):
                        result["platform"] = "shopify"
                        result["confidence"] = 99
                        result["signals"].append("Valid Shopify products.json API (HTTP 200)")
                        return result
                except ValueError:
                    pass

            if r.status_code in (403, 404, 401, 405, 406):
                result["signals"].append(f"Shopify API returned HTTP {r.status_code} (not proof)")
                return result

        except requests.RequestException as e:
            result["signals"].append(f"Shopify API check failed: {type(e).__name__}")

        return result

    def _check_woocommerce(self, html: str, url: str) -> Dict:
        """Check for WooCommerce indicators."""
        result = {"platform": "generic", "confidence": 0, "signals": [], "url": url}
        html_lower = html.lower()

        if "woocommerce" in html_lower:
            result["signals"].append("'woocommerce' keyword in HTML")
            result["confidence"] = 90

        if "wc-blocks" in html_lower or "wc_" in html_lower:
            result["signals"].append("WooCommerce blocks in HTML")
            result["confidence"] = 90

        if "/wp-json/wc/" in html_lower:
            result["signals"].append("WooCommerce REST API in HTML")
            result["confidence"] = 95

        if result["confidence"] > 0:
            result["platform"] = "woocommerce"
            return result

        try:
            r = requests.get(f"{url}/wp-json/wc/v3/products?per_page=1", timeout=self.timeout, headers={"User-Agent": "SIAR-Digital-Platform/1.0"})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    result["platform"] = "woocommerce"
                    result["confidence"] = 95
                    result["signals"].append("WooCommerce REST API confirmed")
                    return result
        except:
            pass

        return result

    def _check_magento(self, html: str, url: str) -> Dict:
        """Check for Magento indicators."""
        result = {"platform": "generic", "confidence": 0, "signals": [], "url": url}
        html_lower = html.lower()

        if "magento" in html_lower or "mage/" in html_lower:
            result["signals"].append("Magento keywords in HTML")
            result["confidence"] = 85
            result["platform"] = "magento"
            return result

        if "/media/catalog/" in html_lower:
            result["signals"].append("Magento media path in HTML")
            result["confidence"] = 85
            result["platform"] = "magento"
            return result

        try:
            r = requests.get(f"{url}/rest/V1/products?limit=1", timeout=self.timeout, headers={"User-Agent": "SIAR-Digital-Platform/1.0"})
            if r.status_code == 200:
                result["platform"] = "magento"
                result["confidence"] = 95
                result["signals"].append("Magento REST API confirmed")
                return result
        except:
            pass

        return result

    def _check_bigcommerce(self, html: str, url: str) -> Dict:
        """Check for BigCommerce indicators."""
        result = {"platform": "generic", "confidence": 0, "signals": [], "url": url}
        html_lower = html.lower()

        if "bigcommerce" in html_lower or "bigcontent" in html_lower:
            result["platform"] = "bigcommerce"
            result["confidence"] = 85
            result["signals"].append("BigCommerce keywords in HTML")
            return result

        if ".cdn11.com" in html_lower or "bcvcdn.com" in html_lower:
            result["platform"] = "bigcommerce"
            result["confidence"] = 85
            result["signals"].append("BigCommerce CDN in HTML")
            return result

        return result

    def _check_wix(self, html: str) -> Dict:
        """Check for Wix indicators."""
        result = {"platform": "generic", "confidence": 0, "signals": []}
        html_lower = html.lower()

        if "wix.com" in html_lower or "wixstatic.com" in html_lower:
            result["platform"] = "wix"
            result["confidence"] = 85
            result["signals"].append("Wix CDN in HTML")
            return result

        if "wix_" in html_lower or "wixdata" in html_lower:
            result["platform"] = "wix"
            result["confidence"] = 80
            result["signals"].append("Wix scripts in HTML")
            return result

        return result

    def _check_squarespace(self, html: str) -> Dict:
        """Check for Squarespace indicators."""
        result = {"platform": "generic", "confidence": 0, "signals": []}
        html_lower = html.lower()

        if "squarespace" in html_lower or "sqspcdn.com" in html_lower:
            result["platform"] = "squarespace"
            result["confidence"] = 85
            result["signals"].append("Squarespace keywords in HTML")
            return result

        return result


def detect_platform(url: str, timeout: int = 15) -> Dict:
    """Functional wrapper for backward compatibility."""
    detector = PlatformDetector(timeout=timeout)
    return detector.detect(url)
