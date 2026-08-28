"""Config-driven validation and completeness checks (two-level model).

A product's stored data looks like::

    { "product": { <product field values> },
      "items":   [ { <item-set field values> }, ... ] }

Philosophy: saving must never lose data, so drafts with missing or invalid
fields are still persisted. Validation returns *warnings* the UI surfaces
(missing required fields, non-numeric prices, duplicate SKUs) rather than
hard-blocking a save. A separate completeness view drives the badges and the
pre-submission summary.
"""
from __future__ import annotations

from . import fields as F


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def clean_value(field: dict, value):
    """Normalise an incoming value to the field's storage shape."""
    if F.is_multi(field):
        if value is None:
            return []
        if isinstance(value, str):
            parts = [v.strip() for v in value.split(",")]
            return [v for v in parts if v]
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip() != ""]
        return [str(value)]
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return value


def _clean_fields(fields: list[dict], raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    for field in fields:
        key = field["key"]
        if key in raw:
            out[key] = clean_value(field, raw.get(key))
        else:
            out[key] = [] if F.is_multi(field) else ""
    return out


def clean_product(raw: dict) -> dict:
    """Return the canonical two-level shape, keeping only known fields."""
    raw = raw if isinstance(raw, dict) else {}
    if "product" in raw or "items" in raw:
        prod_raw = raw.get("product", {})
        items_raw = raw.get("items", []) or []
    else:
        # tolerate a flat legacy payload
        prod_raw = raw
        items_raw = []
    product = _clean_fields(F.product_fields(), prod_raw)
    items = [_clean_fields(F.item_fields(), it) for it in items_raw if isinstance(it, dict)]
    return {"product": product, "items": items}


def _numeric_errors(fields: list[dict], data: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    for field in fields:
        if field.get("type") != "number":
            continue
        value = data.get(field["key"])
        if _is_empty(value):
            continue
        try:
            num = float(str(value).replace(",", ""))
        except (ValueError, TypeError):
            errors[field["key"]] = f"{field['label']} must be a number."
            continue
        if "min" in field and num < field["min"]:
            errors[field["key"]] = f"{field['label']} cannot be less than {field['min']}."
    return errors


def evaluate_product(data: dict) -> dict:
    """Per-product completeness + inline errors (excludes cross-product dup SKU)."""
    data = data if isinstance(data, dict) else {}
    product = data.get("product", {}) or {}
    items = data.get("items", []) or []

    missing: list[str] = []
    for field in F.product_fields():
        if field.get("required") and _is_empty(product.get(field["key"])):
            missing.append(field["label"])

    item_label = F.item_label()
    min_items = F.min_items()
    if len(items) < min_items:
        need = min_items - len(items)
        missing.append(f"At least {min_items} {item_label.lower()}"
                       f"{'s' if min_items != 1 else ''} required")

    item_errors: list[dict] = []
    for idx, it in enumerate(items):
        errs = _numeric_errors(F.item_fields(), it)
        for field in F.item_fields():
            if field.get("required") and _is_empty(it.get(field["key"])):
                missing.append(f"{item_label} {idx + 1}: {field['label']}")
        item_errors.append(errs)

    product_errors = _numeric_errors(F.product_fields(), product)

    complete = (
        not missing
        and not product_errors
        and all(not e for e in item_errors)
    )
    return {
        "complete": complete,
        "missing": missing,
        "product_errors": product_errors,
        "item_errors": item_errors,
    }


def duplicate_sku_values(products) -> set[str]:
    """Lower-cased SKU values that appear on more than one item-set across the
    whole launch (SKUs live at the item-set level)."""
    counts: dict[str, int] = {}
    for p in products:
        for it in (p.get_data().get("items", []) or []):
            sku = (it.get("sku") or "").strip().lower()
            if sku:
                counts[sku] = counts.get(sku, 0) + 1
    return {sku for sku, n in counts.items() if n > 1}


def apply_duplicates(summary: dict, data: dict, dup_skus: set[str]) -> bool:
    """Mark duplicated SKUs on a product's item_errors. Returns True if any."""
    found = False
    items = data.get("items", []) or []
    for idx, it in enumerate(items):
        sku = (it.get("sku") or "").strip().lower()
        if sku and sku in dup_skus:
            found = True
            if idx < len(summary["item_errors"]):
                summary["item_errors"][idx]["sku"] = "Duplicate SKU (used more than once)."
            summary["missing"].append(
                f"{F.item_label()} {idx + 1}: Duplicate SKU")
    if found:
        summary["complete"] = False
    return found
