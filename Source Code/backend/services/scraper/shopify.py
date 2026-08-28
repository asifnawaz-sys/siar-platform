import csv
import html
import re
from pathlib import Path
from urllib.parse import urljoin
import requests

SHOPIFY_COLUMNS = [
    "Handle","Title","Body HTML","Vendor","Product Category","Type","Tags","Published",
    "Option1 Name","Option1 Value","Option2 Name","Option2 Value","Option3 Name","Option3 Value",
    "Variant SKU","Variant Grams","Variant Inventory Tracker","Variant Inventory Qty",
    "Variant Inventory Policy","Variant Fulfillment Service","Variant Price","Variant Compare At Price",
    "Variant Requires Shipping","Variant Taxable","Variant Barcode","Image Src","Image Position",
    "Image Alt Text","Gift Card","SEO Title","SEO Description","Google Shopping / Google Product Category",
    "Variant Image","Variant Weight Unit","Status"
]

def safe_handle(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:255] or "product"

def clean_html(value: str) -> str:
    # Escape dangerous literal HTML only for text-derived fields.
    return html.escape(value or "", quote=False)

def money(value):
    if value is None:
        return ""
    return str(value).strip()

def build_variant_sku(base_sku: str, option_values: list[str], used: set[str]) -> str:
    """Single source of truth for SKU generation."""
    base = (base_sku or "SKU").strip()
    suffix = "-".join(
        re.sub(r"[^A-Za-z0-9]+", "-", x.strip()).strip("-").upper()
        for x in option_values if x and x.strip()
    )
    candidate = f"{base}-{suffix}" if suffix else base
    candidate = re.sub(r"-+", "-", candidate)
    if candidate not in used:
        used.add(candidate)
        return candidate
    i = 2
    while f"{candidate}-{i}" in used:
        i += 1
    final = f"{candidate}-{i}"
    used.add(final)
    return final

def normalize_weight_grams(value, unit="g"):
    if value in (None, ""):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = (unit or "g").lower()
    if u in ("kg", "kilogram", "kilograms"):
        v *= 1000
    elif u in ("lb", "lbs", "pound", "pounds"):
        v *= 453.59237
    return round(v, 3)

def export_shopify_csv(products, output_path: str):
    """Generate Shopify CSV without inventing inventory or variant images."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in products:
        variants = p.get("variants") or [{}]
        images = p.get("images") or []

        for idx, v in enumerate(variants):
            opts = [v.get("option1",""), v.get("option2",""), v.get("option3","")]
            row = {c: "" for c in SHOPIFY_COLUMNS}
            row.update({
                "Handle": p.get("handle",""),
                "Title": p.get("title","") if idx == 0 else "",
                "Body HTML": p.get("body_html","") if idx == 0 else "",
                "Vendor": p.get("vendor","") if idx == 0 else "",
                "Product Category": p.get("category","") if idx == 0 else "",
                "Type": p.get("product_type","") if idx == 0 else "",
                "Tags": p.get("tags","") if idx == 0 else "",
                "Published": "TRUE" if p.get("published", True) and idx == 0 else "",
                "Option1 Name": "Size" if opts[0] else "",
                "Option1 Value": opts[0],
                "Option2 Name": "Color" if opts[1] else "",
                "Option2 Value": opts[1],
                "Option3 Name": "Style" if opts[2] else "",
                "Option3 Value": opts[2],
                "Variant SKU": v.get("sku",""),
                "Variant Grams": "" if v.get("weight_grams") is None else v.get("weight_grams"),
                "Variant Weight Unit": "g" if v.get("weight_grams") is not None else "",
                "Variant Inventory Tracker": v.get("inventory_tracker","shopify") if v.get("inventory_quantity") is not None else "",
                "Variant Inventory Qty": "" if v.get("inventory_quantity") is None else v.get("inventory_quantity"),
                "Variant Inventory Policy": v.get("inventory_policy","deny"),
                "Variant Fulfillment Service": "manual",
                "Variant Price": money(v.get("price")),
                "Variant Compare At Price": money(v.get("compare_at_price")),
                "Variant Requires Shipping": "TRUE",
                "Variant Taxable": "TRUE",
                "Variant Barcode": v.get("barcode",""),
                "SEO Title": p.get("seo_title","") if idx == 0 else "",
                "SEO Description": p.get("seo_description","") if idx == 0 else "",
                "Status": p.get("status","active"),
            })
            # Never assign an image to a variant merely because its index matches.
            if v.get("image_src"):
                row["Variant Image"] = v["image_src"]

            if idx == 0:
                for image_idx, img in enumerate(images, start=1):
                    image_row = row.copy()
                    image_row["Image Src"] = img.get("src","")
                    image_row["Image Position"] = image_idx
                    image_row["Image Alt Text"] = img.get("alt","") or p.get("title","")
                    rows.append(image_row)
            else:
                rows.append(row)

    with output.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=SHOPIFY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return output
