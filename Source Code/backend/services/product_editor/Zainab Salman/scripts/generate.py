#!/usr/bin/env python3
"""
Read Shopify CSV from data/, build product JSON, and inject into product_editor.html.

Run from project root:
    python3 scripts/generate.py
    python3 scripts/generate.py "data/Zainab Salman.csv"
    python3 scripts/generate.py "/full/path/to/file.csv"
"""

import csv
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "product_editor.html"
BASE_URL = "https://zainabsalman.com/products"


def resolve_csv_path(arg):
    if not arg:
        return ROOT / "data" / "Zainab Salman FULL.csv"
    p = Path(arg)
    if not p.is_absolute():
        p = ROOT / p
    return p

# Metafield keys to exclude from components
COMPONENT_EXCLUDE_KEYS = {
    "child_products", "color", "color_switcher", "delivery_timeline",
    "model_height", "model_wearing", "model_wearing_size",
    "parent_fabirc", "parent_prices", "parent_product_handle", "parent_sizes",
    "product_sub_type", "product_disclaimer", "shirt_length", "shirt_style",
    "rts_delivery_timeline_international", "rts_delivery_timeline_local",
}

# Precompute component column indices and display names
def build_component_cols(headers):
    """Return list of (col_idx, display_name, metafield_key) for component columns."""
    result = []
    pattern = re.compile(r'^(.+?)\s+\(product\.metafields\.custom\.([^)]+)\)$')
    for i in range(49, 175):
        m = pattern.match(headers[i])
        if m:
            display_name = m.group(1)
            key = m.group(2)
            if key not in COMPONENT_EXCLUDE_KEYS:
                result.append((i, display_name, key))
    return result


def title_from_handle(handle):
    """Convert a handle to a display title."""
    return ' '.join(w.capitalize() for w in handle.replace('-', ' ').split())


def hidx(headers, name, default):
    """Resolve a column index by exact header name, falling back to a default.

    Newer Shopify exports insert extra columns (e.g. "Variant Image"), which
    shifts the tail columns. Resolving by name keeps both formats working.
    """
    try:
        return headers.index(name)
    except ValueError:
        return default


def safe_float(val):
    """Parse a float from a string, return 0.0 on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def format_price(val):
    """Format a price string to 2 decimal places, or return empty string."""
    v = val.strip() if val else ""
    if not v:
        return ""
    try:
        return f"{float(v):.2f}"
    except ValueError:
        return v


def build_variant(row, option_names_from_first_row, headers):
    """Build a variant dict from a CSV row."""
    # For first row, option names come from the row itself.
    # For subsequent rows, option names are empty in CSV but we keep them empty as-is (matching existing data).
    opt1_name = row[8]
    opt1_val  = row[9]
    opt2_name = row[11]
    opt2_val  = row[12]
    opt3_name = row[14]
    opt3_val  = row[15]

    # item/fabric/size logic: use option names from the first row of the group
    o1n, o2n, o3n = option_names_from_first_row

    item   = opt1_val if o1n.lower() == "item"   else (opt1_val if o1n else "")
    fabric = opt2_val if o2n.lower() == "fabric"  else (opt2_val if o2n else "")
    size   = opt3_val if o3n.lower() == "size"    else (opt3_val if o3n else "")

    # If options aren't Item/Fabric/Size we still populate from option values
    if o1n and o1n.lower() != "item":
        item = opt1_val
    if o2n and o2n.lower() != "fabric":
        fabric = opt2_val
    if o3n and o3n.lower() != "size":
        size = opt3_val

    status_val = row[hidx(headers, "Status", 192)].strip()
    status = status_val if status_val else "active"

    # inventory qty: keep as string (matching existing data)
    inv_qty = row[20].strip() if row[20].strip() else "0"

    # image: col 32 (Image Src)
    image = row[32].strip()

    return {
        "option1Name":     opt1_name,
        "option1Value":    opt1_val,
        "option2Name":     opt2_name,
        "option2Value":    opt2_val,
        "option3Name":     opt3_name,
        "option3Value":    opt3_val,
        "item":            item,
        "fabric":          fabric,
        "size":            size,
        "sku":             row[17].strip(),
        "grams":           row[18].strip(),
        "inventoryTracker":row[19].strip(),
        "inventoryQty":    inv_qty,
        "inventoryPolicy": row[21].strip(),
        "fulfillment":     row[22].strip(),
        "price":           format_price(row[23]),
        "compareAtPrice":  format_price(row[24]),
        "requiresShipping":row[25].strip(),
        "taxable":         row[26].strip(),
        "barcode":         row[31].strip(),
        "weightUnit":      row[hidx(headers, "Variant Weight Unit", 189)].strip(),
        "taxCode":         row[hidx(headers, "Variant Tax Code", 190)].strip(),
        "costPerItem":     row[hidx(headers, "Cost per item", 191)].strip(),
        "status":          status,
        "image":           image,
    }


def build_child(handle, grp, headers):
    """Build a child product dict from its group of CSV rows."""
    first = grp[0]
    option_names_from_first = (first[8], first[11], first[14])
    o1n, o2n, o3n = option_names_from_first

    variants = [build_variant(row, option_names_from_first, headers) for row in grp]

    # item/fabric/size from first variant
    first_v = variants[0]
    item   = first_v["item"]
    fabric = first_v["fabric"]
    size   = first_v["size"]

    # price min/max from all variants
    prices = []
    for v in variants:
        p = v["price"]
        if p:
            try:
                prices.append(float(p))
            except ValueError:
                pass
    price_min = min(prices) if prices else 0.0
    price_max = max(prices) if prices else 0.0

    # image = first non-empty Image Src
    image = ""
    for row in grp:
        if row[32].strip():
            image = row[32].strip()
            break

    # tags from first row
    tags = first[6].strip()

    # subtype
    subtype = first[139].strip()

    # status
    status = first[hidx(headers, "Status", 192)].strip() if first[hidx(headers, "Status", 192)].strip() else "active"
    published = first[7].strip() if first[7].strip() else "true"

    return {
        "handle":       handle,
        "title":        first[1].strip(),
        "subtype":      subtype,
        "vendor":       first[3].strip(),
        "type":         first[5].strip(),
        "status":       status,
        "published":    published,
        "item":         item,
        "fabric":       fabric,
        "size":         size,
        "priceMin":     price_min,
        "priceMax":     price_max,
        "variantCount": len(variants),
        "image":        image,
        "url":          f"{BASE_URL}/{handle}",
        "sku":          first[17].strip(),
        "grams":        first[18].strip(),
        "inventory":    first[20].strip(),
        "tags":         tags,
        "variants":     variants,
    }


def build_parent(parent_handle, groups, component_cols, headers):
    """Build a parent product dict.

    If parent_handle exists in groups, use its first row for metadata.
    Otherwise synthesize a minimal parent.
    """
    if parent_handle in groups:
        grp = groups[parent_handle]
        first = grp[0]

        title        = first[1].strip()
        description  = first[2].strip()
        vendor       = first[3].strip()
        ptype        = first[5].strip()
        tags         = first[6].strip()
        published    = first[7].strip() if first[7].strip() else "true"
        status       = first[hidx(headers, "Status", 192)].strip() if first[hidx(headers, "Status", 192)].strip() else "active"
        image        = ""
        for row in grp:
            if row[32].strip():
                image = row[32].strip()
                break
        image_alt        = first[34].strip()
        color            = first[69].strip()
        delivery         = first[77].strip()
        model_height     = first[117].strip()
        model_wearing    = first[119].strip()
        shirt_length     = first[157].strip()
        shirt_style      = first[159].strip()
        parent_fabric    = first[127].strip()
        parent_prices    = first[128].strip()
        parent_sizes     = first[130].strip()
        child_prods_raw  = first[64].strip()

        # variant count / price min-max from the group rows (parent product itself)
        option_names = (first[8], first[11], first[14])
        variants = [build_variant(row, option_names, headers) for row in grp]
        prices = []
        for v in variants:
            p = v["price"]
            if p:
                try:
                    prices.append(float(p))
                except ValueError:
                    pass
        price_min = min(prices) if prices else 0.0
        price_max = max(prices) if prices else 0.0
        variant_count = len(variants)

        # components from component_cols on first row
        components = []
        for col_idx, display_name, _key in component_cols:
            val = first[col_idx].strip()
            if val:
                components.append({"name": display_name, "value": val})

    else:
        # Synthetic parent – not present in CSV
        title         = title_from_handle(parent_handle)
        description   = ""
        vendor        = ""
        ptype         = ""
        tags          = ""
        published     = "true"
        status        = "active"
        image         = ""
        image_alt     = ""
        color         = ""
        delivery      = ""
        model_height  = ""
        model_wearing = ""
        shirt_length  = ""
        shirt_style   = ""
        parent_fabric = ""
        parent_prices = ""
        parent_sizes  = ""
        child_prods_raw = ""
        price_min     = 0.0
        price_max     = 0.0
        variant_count = 0
        components    = []

    return {
        "handle":           parent_handle,
        "title":            title,
        "description":      description,
        "vendor":           vendor,
        "type":             ptype,
        "tags":             tags,
        "published":        published,
        "status":           status,
        "image":            image,
        "imageAlt":         image_alt,
        "url":              f"{BASE_URL}/{parent_handle}",
        "color":            color,
        "delivery":         delivery,
        "modelHeight":      model_height,
        "modelWearingSize": model_wearing,
        "shirtLength":      shirt_length,
        "shirtStyle":       shirt_style,
        "parentFabric":     parent_fabric,
        "parentSizes":      parent_sizes,
        "parentPrices":     parent_prices,
        "childProductsRaw": child_prods_raw,
        "priceMin":         price_min,
        "priceMax":         price_max,
        "variantCount":     variant_count,
        "components":       components,
        "children":         [],  # filled later
    }


def main():
    csv_path = resolve_csv_path(sys.argv[1] if len(sys.argv) > 1 else None)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # ── 1. Read CSV ──────────────────────────────────────────────────────────
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = list(next(reader))
        rows = list(reader)

    component_cols = build_component_cols(headers)

    # Group rows by handle, preserving first-appearance order
    groups = OrderedDict()
    for row in rows:
        h = row[0].strip()
        if not h:
            continue
        if h not in groups:
            groups[h] = []
        groups[h].append(row)

    # ── 2. Determine parent handles ──────────────────────────────────────────
    # A handle is a "parent" if:
    #   (a) its subtype is "Parent Product", OR
    #   (b) another handle has it as parent_product_handle (excluding self-references)
    # Additionally, standalone handles (no parent, not referenced) are also top-level parents.

    referenced_as_parent = set()
    for h, grp in groups.items():
        pph = grp[0][129].strip()
        if pph and pph != h:
            referenced_as_parent.add(pph)

    is_child = {}  # handle -> parent_handle (if it has a real parent)
    for h, grp in groups.items():
        pph = grp[0][129].strip()
        if pph and pph != h:
            is_child[h] = pph

    explicit_parents = {h for h, grp in groups.items() if grp[0][139].strip() == "Parent Product"}

    # All parent handles: explicit "Parent Product" rows only (matches viewer / Shopify export)
    all_parent_handles_set = set(explicit_parents)

    # Determine order of parents:
    # 1. Handles present in CSV that are parents → in CSV first-appearance order
    # 2. Synthetic parents → ordered by first appearance of any of their children in CSV

    # Map: parent_handle -> index of earliest row in CSV (for ordering)
    parent_order = {}

    # Go through all groups in order and assign order index
    row_index = 0
    for h, grp in groups.items():
        if h in all_parent_handles_set and h not in parent_order:
            parent_order[h] = row_index
        # Also update order for synthetic parents based on child appearance
        pph = grp[0][129].strip()
        if pph and pph != h and pph not in parent_order:
            parent_order[pph] = row_index
        row_index += len(grp)

    # Sort parents by their order index
    sorted_parent_handles = sorted(all_parent_handles_set, key=lambda h: parent_order.get(h, 999999))

    # ── 3. Build children map: parent_handle -> [child_handles in CSV order] ──
    # We iterate the groups in CSV order to preserve child ordering.
    # Primary source: col129 (parent_product_handle) on child rows (excluding self-refs).
    # Secondary source: col64 (child_products) on parent rows, to catch self-referencing
    # children whose col129 points to themselves (e.g. ella-corset).

    children_map = OrderedDict()
    for parent in sorted_parent_handles:
        children_map[parent] = []

    # Primary: col129-based
    for h, grp in groups.items():
        if h in is_child:
            pph = is_child[h]
            if pph not in children_map:
                children_map[pph] = []
            if h not in children_map[pph]:
                children_map[pph].append(h)

    # Secondary: col64-based (for explicit parents whose children may self-reference)
    for h, grp in groups.items():
        if grp[0][139].strip() == "Parent Product":
            cp_raw = grp[0][64].strip()
            if cp_raw:
                # col64 may be semicolon-separated handle list
                child_handles_from_col64 = [c.strip() for c in cp_raw.replace(";", ",").split(",") if c.strip()]
                if h not in children_map:
                    children_map[h] = []
                for ch in child_handles_from_col64:
                    if ch in groups and ch not in children_map[h]:
                        children_map[h].append(ch)

    # ── 4. Build products array ──────────────────────────────────────────────
    products = []
    for parent_handle in sorted_parent_handles:
        parent = build_parent(parent_handle, groups, component_cols, headers)

        # Build children
        child_handles = children_map.get(parent_handle, [])
        children = []
        for child_handle in child_handles:
            if child_handle in groups:
                child = build_child(child_handle, groups[child_handle], headers)
                children.append(child)
            # If child not in CSV (shouldn't happen with our logic), skip

        parent["children"] = children
        products.append(parent)

    # ── 5. Serialize to JSON ─────────────────────────────────────────────────
    new_json = json.dumps(products, ensure_ascii=False, separators=(",", ":"))

    # Source CSV rows per handle (for Shopify-format export round-trip)
    ncol = len(headers)
    source_rows = {}
    for h, grp in groups.items():
        source_rows[h] = [row + [""] * (ncol - len(row)) for row in grp]

    component_map = {display_name: col_idx for col_idx, display_name, _key in component_cols}

    headers_json = json.dumps(headers, ensure_ascii=False, separators=(",", ":"))
    source_rows_json = json.dumps(source_rows, ensure_ascii=False, separators=(",", ":"))
    component_map_json = json.dumps(component_map, ensure_ascii=False, separators=(",", ":"))
    csv_filename_json = json.dumps(csv_path.name, ensure_ascii=False)

    # ── 6. Inject into HTML ──────────────────────────────────────────────────
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    inject_block = (
        "window.ZS_PRODUCTS = " + new_json + ";\n"
        "window.ZS_CSV_HEADERS = " + headers_json + ";\n"
        "window.ZS_SOURCE_ROWS = " + source_rows_json + ";\n"
        "window.ZS_COMPONENT_MAP = " + component_map_json + ";\n"
        "window.ZS_CSV_FILENAME = " + csv_filename_json + ";"
    )

    pattern = re.compile(r"(<script>)window\.ZS_PRODUCTS[\s\S]*?(</script>)", re.MULTILINE)
    match = pattern.search(html)
    if not match:
        raise ValueError("Could not find data script block in product_editor.html")

    new_html = html[: match.start()] + match.group(1) + inject_block + match.group(2) + html[match.end() :]

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"Done. Generated {len(products)} parent products from {csv_path.name}.")
    child_total = sum(len(p["children"]) for p in products)
    print(f"Total children: {child_total}")
    print(f"Parent handles: {[p['handle'] for p in products]}")


if __name__ == "__main__":
    main()
