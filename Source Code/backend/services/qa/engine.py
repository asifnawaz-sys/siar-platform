"""
Comprehensive product QA engine checking all product and variant fields.
Returns severity-based issues and pass/review/fail grades.
"""

import logging
import re
from typing import List, Dict, Tuple, Any
from urllib.parse import urlparse

log = logging.getLogger("siar.qa")

SEVERITY_WEIGHTS = {
    "CRITICAL": 50,
    "HIGH": 20,
    "MEDIUM": 10,
    "LOW": 5,
}


class QAEngine:
    """Comprehensive quality assurance for e-commerce product data."""

    @staticmethod
    def validate_url(url: str) -> bool:
        """Check if URL is valid HTTP(S)."""
        try:
            result = urlparse(url)
            return result.scheme in ("http", "https") and result.netloc
        except Exception:
            return False

    @staticmethod
    def is_valid_price(price: Any) -> bool:
        """Check if price is a valid number."""
        try:
            if price is None or price == "":
                return False
            p = float(str(price).replace(",", ""))
            return p >= 0
        except (ValueError, TypeError):
            return False

    @staticmethod
    def is_valid_weight(weight: Any) -> bool:
        """Check if weight is valid."""
        try:
            if weight is None or weight == "":
                return False
            w = float(str(weight))
            return w > 0
        except (ValueError, TypeError):
            return False

    @classmethod
    def qa_product(cls, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive QA check for a single product.

        Returns:
            {
                "score": 0-100,
                "grade": "PASS" | "REVIEW" | "FAIL",
                "critical_issues": [...],
                "high_issues": [...],
                "medium_issues": [...],
                "low_issues": [...],
                "total_variants": N,
                "variant_issues": N,
                "recommendations": [...]
            }
        """

        issues_by_severity = {
            "CRITICAL": [],
            "HIGH": [],
            "MEDIUM": [],
            "LOW": [],
        }

        recommendations = []

        # ═════════════════════════════════════════════════════════════════════
        # PRODUCT-LEVEL CHECKS
        # ═════════════════════════════════════════════════════════════════════

        title = str(product.get("title", "")).strip()
        if not title:
            issues_by_severity["CRITICAL"].append("Missing product title")
        elif len(title) < 3:
            issues_by_severity["HIGH"].append(f"Title too short ({len(title)} chars)")
        elif len(title) > 255:
            issues_by_severity["MEDIUM"].append(f"Title very long ({len(title)} chars, max 255)")

        handle = str(product.get("handle", "")).strip()
        if not handle:
            issues_by_severity["CRITICAL"].append("Missing product handle")
        elif not re.match(r'^[a-z0-9\-]+$', handle):
            issues_by_severity["HIGH"].append(f"Invalid handle format: '{handle}'")

        # Body/Description
        body = str(product.get("body_html", "")).strip()
        if not body:
            issues_by_severity["MEDIUM"].append("Missing product description")

        # Vendor
        vendor = str(product.get("vendor", "")).strip()
        if not vendor:
            issues_by_severity["LOW"].append("Missing vendor")
        else:
            recommendations.append("Vendor populated: good for fulfillment tracking")

        # Product Type
        ptype = str(product.get("product_type", "")).strip()
        if not ptype:
            issues_by_severity["MEDIUM"].append("Missing product type/category")

        # Tags
        tags = product.get("tags", "")
        if tags and isinstance(tags, str):
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if len(tag_list) > 20:
                issues_by_severity["LOW"].append(f"Too many tags ({len(tag_list)}, recommend <20)")

        # Images
        images = product.get("images") or []
        if not images:
            issues_by_severity["HIGH"].append("No product images")
        elif len(images) == 1:
            issues_by_severity["MEDIUM"].append("Only 1 image (recommend 3+)")
            recommendations.append("Add more product images for better conversions")
        else:
            recommendations.append(f"Good: {len(images)} product images")

        # Validate image URLs
        for i, img in enumerate(images, 1):
            img_url = img.get("src", "") if isinstance(img, dict) else str(img)
            if img_url and not cls.validate_url(img_url):
                issues_by_severity["HIGH"].append(f"Image {i}: Invalid URL '{img_url[:50]}'")

        # SEO
        seo_title = str(product.get("seo_title", "")).strip()
        seo_desc = str(product.get("seo_description", "")).strip()
        if not seo_title and not seo_desc:
            issues_by_severity["LOW"].append("Missing SEO title and description")
        elif not seo_title:
            issues_by_severity["LOW"].append("Missing SEO title")
        elif not seo_desc:
            issues_by_severity["LOW"].append("Missing SEO description")
        else:
            recommendations.append("SEO metadata complete")

        # ═════════════════════════════════════════════════════════════════════
        # VARIANT-LEVEL CHECKS
        # ═════════════════════════════════════════════════════════════════════

        variants = product.get("variants") or []
        variant_issues_count = 0

        if not variants:
            issues_by_severity["CRITICAL"].append("No variants defined")
        elif len(variants) > 100:
            issues_by_severity["HIGH"].append(f"Too many variants ({len(variants)}). May exceed Shopify limits. Recommend consolidating.")
            recommendations.append(f"Consider consolidating {len(variants)} variants into fewer options")

        for var_idx, variant in enumerate(variants, 1):
            var_issues = 0

            # SKU checks
            sku = str(variant.get("sku", "")).strip()
            if not sku:
                issues_by_severity["CRITICAL"].append(f"Variant {var_idx}: Missing SKU")
                var_issues += 1
            elif len(sku) > 255:
                issues_by_severity["MEDIUM"].append(f"Variant {var_idx}: SKU too long ({len(sku)})")
                var_issues += 1

            # Price checks
            price = variant.get("price")
            if not cls.is_valid_price(price):
                issues_by_severity["CRITICAL"].append(f"Variant {var_idx}: Missing or invalid price")
                var_issues += 1

            # Compare-at price checks
            cap = variant.get("compare_at_price")
            if cap and cls.is_valid_price(cap):
                try:
                    p = float(str(price).replace(",", ""))
                    c = float(str(cap).replace(",", ""))
                    if c <= p:
                        issues_by_severity["MEDIUM"].append(f"Variant {var_idx}: Compare-at price (${c}) not higher than price (${p})")
                        var_issues += 1
                except (ValueError, TypeError):
                    pass

            # Inventory checks
            inv_qty = variant.get("inventory_quantity")
            inv_status = variant.get("inventory_policy")
            if inv_qty is None and not inv_status:
                issues_by_severity["MEDIUM"].append(f"Variant {var_idx}: No inventory quantity or status")
                var_issues += 1

            # Weight checks
            weight = variant.get("weight_grams")
            if weight is not None:
                if not cls.is_valid_weight(weight):
                    issues_by_severity["MEDIUM"].append(f"Variant {var_idx}: Invalid weight ({weight})")
                    var_issues += 1
                else:
                    weight_unit = variant.get("weight_unit", "g")
                    if weight_unit != "g":
                        issues_by_severity["HIGH"].append(f"Variant {var_idx}: Weight unit should be 'g', not '{weight_unit}'")
                        var_issues += 1

            # Barcode checks
            barcode = variant.get("barcode", "")
            if barcode and not re.match(r'^[0-9]{8,}$', barcode):
                issues_by_severity["LOW"].append(f"Variant {var_idx}: Barcode format suspicious ({barcode})")
                var_issues += 1

            # Option values
            opt1 = variant.get("option1", "")
            opt2 = variant.get("option2", "")
            opt3 = variant.get("option3", "")
            if not (opt1 or opt2 or opt3):
                issues_by_severity["MEDIUM"].append(f"Variant {var_idx}: No option values defined")
                var_issues += 1

            # Variant image (should only be set if confirmed relationship exists)
            var_img = variant.get("image_src", "")
            if var_img and not cls.validate_url(var_img):
                issues_by_severity["HIGH"].append(f"Variant {var_idx}: Invalid variant image URL")
                var_issues += 1

            variant_issues_count += var_issues

        if variants:
            recommendations.append(f"Checked {len(variants)} variants")

        # ═════════════════════════════════════════════════════════════════════
        # SCORE CALCULATION
        # ═════════════════════════════════════════════════════════════════════

        total_issues = sum(len(v) for v in issues_by_severity.values())
        total_penalty = sum(len(v) * SEVERITY_WEIGHTS[k] for k, v in issues_by_severity.items())

        # Score: 100 minus penalties (capped at 0)
        score = max(0, 100 - total_penalty)

        # Grade
        if score >= 90:
            grade = "PASS"
        elif score >= 70:
            grade = "REVIEW"
        else:
            grade = "FAIL"

        return {
            "score": score,
            "grade": grade,
            "total_issues": total_issues,
            "critical_issues": issues_by_severity["CRITICAL"],
            "high_issues": issues_by_severity["HIGH"],
            "medium_issues": issues_by_severity["MEDIUM"],
            "low_issues": issues_by_severity["LOW"],
            "total_variants": len(variants),
            "variant_issues": variant_issues_count,
            "recommendations": recommendations,
        }


def qa_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Functional wrapper for backward compatibility."""
    return QAEngine.qa_product(product)
