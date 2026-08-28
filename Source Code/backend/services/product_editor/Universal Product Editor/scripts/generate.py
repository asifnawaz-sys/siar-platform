#!/usr/bin/env python3
"""
Universal product editor generator.

Reads any brand's Shopify product CSV export, builds a FLAT product model
(product -> variants, no parent/child hierarchy), and injects it into
product_editor.html.

Unlike the Zainab Salman generator, this script does NOT assume fixed
column positions for metafields. Every column is resolved by its header
name, so it keeps working even if a brand's CSV has more/fewer metafields
or the columns shift around. Standard Shopify columns are also resolved by
name (with the common Shopify export position as a fallback default).

Run from project root:
    python3 scripts/generate.py "data/Brand Name.csv"
    python3 scripts/generate.py "data/Brand Name.csv" --base-url https://brand.com/products
"""

import argparse
import csv
import json
import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "product_editor.html"

# Standard Shopify export columns: header name -> fallback index if the
# name isn't found (keeps working even against older/newer export layouts).
STD_COLUMNS = {
    "handle":            ("Handle", 0),
    "title":             ("Title", 1),
    "body":              ("Body (HTML)", 2),
    "vendor":            ("Vendor", 3),
    "type":              ("Type", 5),
    "tags":               ("Tags", 6),
    "published":         ("Published", 7),
    "option1Name":       ("Option1 Name", 8),
    "option1Value":      ("Option1 Value", 9),
    "option2Name":       ("Option2 Name", 11),
    "option2Value":      ("Option2 Value", 12),
    "option3Name":       ("Option3 Name", 14),
    "option3Value":      ("Option3 Value", 15),
    "sku":               ("Variant SKU", 17),
    "grams":             ("Variant Grams", 18),
    "invTracker":        ("Variant Inventory Tracker", 19),
    "invQty":            ("Variant Inventory Qty", 20),
    "invPolicy":         ("Variant Inventory Policy", 21),
    "fulfillment":       ("Variant Fulfillment Service", 22),
    "price":             ("Variant Price", 23),
    "compareAt":         ("Variant Compare At Price", 24),
    "requiresShipping":  ("Variant Requires Shipping", 25),
    "taxable":           ("Variant Taxable", 26),
    "barcode":           ("Variant Barcode", 31),
    "imageSrc":          ("Image Src", 32),
    "imagePosition":     ("Image Position", 33),
    "imageAlt":          ("Image Alt Text", 34),
    "variantImage":      ("Variant Image", 189),
    "weightUnit":        ("Variant Weight Unit", 190),
    "taxCode":           ("Variant Tax Code", 191),
    "costPerItem":       ("Cost per item", 192),
    "status":            ("Status", 193),
}

# New/common product-level metafields. Each maps to a list of candidate
# metafield keys (product.metafields.custom.<key>) to look for in the CSV
# header row, in priority order. A brand's CSV may not have all of these
# yet -- fields with no matching column are simply left blank/editable in
# the UI but won't round-trip into the exported CSV until the metafield
# is created in Shopify.
FIELD_KEY_CANDIDATES = {
    "color":             ["color"],
    "deliveryTimeline":  ["delivery_timeline", "rts_delivery_timeline_local", "rts_delivery_timeline_international"],
    "modelHeight":       ["model_height"],
    "modelWearingSize":  ["model_wearing_size", "model_wearing"],
    "style":             ["style", "shirt_style"],
    "lengthOfTop":       ["length_of_top"],
    "lengthOfBottom":    ["length_of_bottom"],
    "material":          ["material"],
    "careInstructions":  ["care_instructions", "care_instruction", "wash_care"],
}

METAFIELD_PATTERN = re.compile(r'^(.+?)\s+\(product\.metafields\.custom\.([^)]+)\)$')


def hidx(headers, name, default):
    """Resolve a column index by exact header name, falling back to a default."""
    try:
        return headers.index(name)
    except ValueError:
        return default


def build_std_cols(headers):
    return {key: hidx(headers, name, default) for key, (name, default) in STD_COLUMNS.items()}


def build_metafield_cols(headers):
    """Map metafield key -> column index for every custom metafield column."""
    cols = {}
    for i, h in enumerate(headers):
        m = METAFIELD_PATTERN.match(h)
        if m:
            cols[m.group(2)] = i
    return cols


def build_field_cols(metafield_cols):
    """Resolve our 9 tracked fields to column indices where a matching metafield exists."""
    field_cols = {}
    for field, candidates in FIELD_KEY_CANDIDATES.items():
        for key in candidates:
            if key in metafield_cols:
                field_cols[field] = metafield_cols[key]
                break
    return field_cols


def get(row, idx, default=""):
    if idx is None or idx >= len(row):
        return default
    return row[idx]


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def format_price(val):
    v = val.strip() if val else ""
    if not v:
        return ""
    try:
        return f"{float(v):.2f}"
    except ValueError:
        return v


def is_variant_row(row, std):
    """Shopify CSVs can include extra rows per handle that only carry an
    additional product image (Handle + Image Src/Position only, no option
    values, SKU, or price). Those aren't real variants and must not be
    shown/edited as one."""
    for key in ("option1Value", "option2Value", "option3Value", "sku", "price"):
        if get(row, std[key]).strip():
            return True
    return False


def build_variant(row, std):
    opt1_name = get(row, std["option1Name"])
    opt1_val = get(row, std["option1Value"])
    opt2_name = get(row, std["option2Name"])
    opt2_val = get(row, std["option2Value"])
    opt3_name = get(row, std["option3Name"])
    opt3_val = get(row, std["option3Value"])

    # Option1/2/3 are expected to be Item/Fabric/Size (matches how brand
    # CSVs are set up for this tool), but we keep the raw values regardless
    # of the option names actually present, so odd/legacy exports still work.
    item, fabric, size = opt1_val, opt2_val, opt3_val

    status_val = get(row, std["status"]).strip()
    status = status_val if status_val else "active"
    inv_qty = get(row, std["invQty"]).strip() or "0"

    return {
        "option1Name":      opt1_name,
        "option1Value":     opt1_val,
        "option2Name":      opt2_name,
        "option2Value":     opt2_val,
        "option3Name":      opt3_name,
        "option3Value":     opt3_val,
        "item":             item,
        "fabric":           fabric,
        "size":             size,
        "sku":              get(row, std["sku"]).strip(),
        "grams":            get(row, std["grams"]).strip(),
        "inventoryTracker": get(row, std["invTracker"]).strip(),
        "inventoryQty":     inv_qty,
        "inventoryPolicy":  get(row, std["invPolicy"]).strip(),
        "fulfillment":      get(row, std["fulfillment"]).strip(),
        "price":            format_price(get(row, std["price"])),
        "compareAtPrice":   format_price(get(row, std["compareAt"])),
        "requiresShipping": get(row, std["requiresShipping"]).strip(),
        "taxable":          get(row, std["taxable"]).strip(),
        "barcode":          get(row, std["barcode"]).strip(),
        "weightUnit":       get(row, std["weightUnit"]).strip(),
        "taxCode":          get(row, std["taxCode"]).strip(),
        "costPerItem":      get(row, std["costPerItem"]).strip(),
        "status":           status,
        "image":            get(row, std["imageSrc"]).strip(),
    }


def build_product(handle, grp, std, field_cols, base_url):
    first = grp[0]
    variants = []
    row_kinds = []
    for idx, row in enumerate(grp):
        if is_variant_row(row, std):
            v = build_variant(row, std)
            v["_sourceIndex"] = idx
            variants.append(v)
            row_kinds.append("variant")
        else:
            row_kinds.append("image")

    prices = [safe_float(v["price"]) for v in variants]
    prices = [p for p in prices if p is not None]
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0

    image = ""
    for row in grp:
        src = get(row, std["imageSrc"]).strip()
        if src:
            image = src
            break

    status_val = get(first, std["status"]).strip()
    status = status_val if status_val else "active"
    published = get(first, std["published"]).strip() or "true"

    product = {
        "handle":      handle,
        "title":       get(first, std["title"]).strip(),
        "description": get(first, std["body"]).strip(),
        "vendor":      get(first, std["vendor"]).strip(),
        "type":        get(first, std["type"]).strip(),
        "tags":        get(first, std["tags"]).strip(),
        "published":   published,
        "status":      status,
        "image":       image,
        "imageAlt":    get(first, std["imageAlt"]).strip(),
        "url":         f"{base_url}/{handle}" if base_url else "",
        "priceMin":    price_min,
        "priceMax":    price_max,
        "variantCount": len(variants),
        "variants":    variants,
    }
    for field in FIELD_KEY_CANDIDATES:
        col = field_cols.get(field)
        product[field] = get(first, col).strip() if col is not None else ""
    return product, row_kinds


def resolve_csv_path(arg):
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / p
    return p


def main():
    parser = argparse.ArgumentParser(description="Generate a universal product_editor.html from a Shopify CSV export.")
    parser.add_argument("csv_path", help="Path to the Shopify product CSV export (relative to project root or absolute)")
    parser.add_argument("--base-url", default="", help="Base product URL, e.g. https://brand.com/products (optional)")
    args = parser.parse_args()

    csv_path = resolve_csv_path(args.csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = list(next(reader))
        rows = list(reader)

    std = build_std_cols(headers)
    metafield_cols = build_metafield_cols(headers)
    field_cols = build_field_cols(metafield_cols)

    groups = OrderedDict()
    for row in rows:
        h = get(row, std["handle"]).strip()
        if not h:
            continue
        groups.setdefault(h, []).append(row)

    products = []
    row_kinds_map = {}
    for handle, grp in groups.items():
        product, row_kinds = build_product(handle, grp, std, field_cols, args.base_url.rstrip("/"))
        products.append(product)
        row_kinds_map[handle] = row_kinds

    ncol = len(headers)
    source_rows = {h: [row + [""] * (ncol - len(row)) for row in grp] for h, grp in groups.items()}

    new_json = json.dumps(products, ensure_ascii=False, separators=(",", ":"))
    headers_json = json.dumps(headers, ensure_ascii=False, separators=(",", ":"))
    source_rows_json = json.dumps(source_rows, ensure_ascii=False, separators=(",", ":"))
    row_kinds_json = json.dumps(row_kinds_map, ensure_ascii=False, separators=(",", ":"))
    std_cols_json = json.dumps(std, ensure_ascii=False, separators=(",", ":"))
    field_cols_json = json.dumps(field_cols, ensure_ascii=False, separators=(",", ":"))
    csv_filename_json = json.dumps(csv_path.name, ensure_ascii=False)

    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    inject_block = (
        "window.UPE_PRODUCTS = " + new_json + ";\n"
        "window.UPE_CSV_HEADERS = " + headers_json + ";\n"
        "window.UPE_SOURCE_ROWS = " + source_rows_json + ";\n"
        "window.UPE_SOURCE_ROW_KINDS = " + row_kinds_json + ";\n"
        "window.UPE_STD_COLS = " + std_cols_json + ";\n"
        "window.UPE_FIELD_COLS = " + field_cols_json + ";\n"
        "window.UPE_CSV_FILENAME = " + csv_filename_json + ";"
    )

    pattern = re.compile(r"(<script>)window\.UPE_PRODUCTS[\s\S]*?(</script>)", re.MULTILINE)
    match = pattern.search(html)
    if not match:
        raise ValueError("Could not find data script block in product_editor.html")

    new_html = html[: match.start()] + match.group(1) + inject_block + match.group(2) + html[match.end():]

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    missing_fields = [f for f in FIELD_KEY_CANDIDATES if f not in field_cols]
    print(f"Done. Generated {len(products)} products from {csv_path.name}.")
    if missing_fields:
        print("Note: no matching metafield column found for: " + ", ".join(missing_fields))
        print("These fields are still editable in the UI, but edits won't be written back into the exported CSV")
        print("until you add matching metafields (product.metafields.custom.<key>) in Shopify for this brand.")


if __name__ == "__main__":
    main()
