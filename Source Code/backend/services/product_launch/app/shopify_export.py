"""Shopify product-import CSV generation (variant-per-row), config-driven.

Maps our two-level model onto Shopify's product CSV, entirely from the
``shopify`` block in ``field_config.json`` (nothing brand-specific is hard-coded):

* One product  -> one ``Handle`` shared by all its rows.
* Up to three **options** (Shopify's maximum). Each option reads a product- or
  item-level field. Exactly one option is marked ``explode`` (Size): its list
  values create the separate **variant rows**. Non-exploded options with a list
  value (Fabric) are joined into a single value.
* So Biscuit Fold with a 2-piece and a 3-piece item-set, each in S/M/L/XL, gives
  8 variant rows: Option1=Item, Option2=Fabric, Option3=Size.
* Vendor/Type/Body/Title/Images come from the mapped product fields; every other
  product field (Color, Length, Care, Category, …) is written as a **metafield**
  column. Product-level values appear only on each product's first row.
* Additional images become their own ``Handle + Image Src + Image Position`` rows.

Default mapping (change it in field_config.json → "shopify"):
    Vendor = Collection Name · Type = Product Type
    Option1 = Item · Option2 = Fabric · Option3 = Size
    Color + extra fields = metafields
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from html import escape

from . import fields as F
from .csv_export import safe_filename_part

BASE_COLUMNS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type",
    "Tags", "Published",
    "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
    "Option3 Name", "Option3 Value",
    "Variant SKU", "Variant Grams", "Variant Inventory Tracker",
    "Variant Inventory Qty", "Variant Inventory Policy",
    "Variant Fulfillment Service", "Variant Price", "Variant Compare At Price",
    "Variant Requires Shipping", "Variant Taxable", "Variant Barcode",
    "Image Src", "Image Position", "Image Alt Text", "Gift Card",
    "SEO Title", "SEO Description", "Variant Image", "Variant Weight Unit",
    "Status",
]

DEFAULTS = {
    "title_field": "title", "body_field": "description",
    "vendor_field": "collection", "type_field": "product_type",
    "images_field": "images", "tags_fields": [],
    "sku_field": "sku", "price_field": "price",
    "compare_at_field": "compare_at_price", "append_option_to_sku": True,
    "weight_unit": "g", "published": True, "status": "draft",
    "options": [], "metafields": [], "metafield_namespace": "custom",
    "metafield_header": "{name} (product.metafields.{namespace}.{key})",
}


def _cfg() -> dict:
    merged = dict(DEFAULTS)
    merged.update(F.get_config().get("shopify", {}) or {})
    return merged


def export_filename(launch) -> str:
    return f"{safe_filename_part(launch.brand_name)}_Shopify_Import_{launch.token}.csv"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "product"


def _num(value) -> str:
    return "" if value is None else str(value).replace(",", "").strip()


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _body_html(text: str) -> str:
    paras = [p.strip() for p in (text or "").split("\n") if p.strip()]
    return "".join(f"<p>{escape(p)}</p>" for p in paras)


def _flat(value, joiner=", ") -> str:
    if isinstance(value, list):
        return joiner.join(str(v) for v in value if str(v).strip())
    return "" if value is None else str(value)


def _metafield_columns(cfg: dict) -> list[str]:
    ns = cfg["metafield_namespace"]
    tmpl = cfg["metafield_header"]
    return [
        tmpl.format(name=m.get("name", m["key"]), namespace=m.get("namespace", ns),
                    key=m["key"], type=m.get("type", "single_line_text_field"))
        for m in cfg["metafields"]
    ]


def _opt_value(option, item_set, product) -> str:
    src = item_set if option.get("level", "item") == "item" else product
    return _flat(src.get(option["field"]), option.get("join", " / "))


def build_csv(launch) -> str:
    cfg = _cfg()
    options = cfg["options"]
    explode = next((o for o in options if o.get("explode")), None)

    columns = BASE_COLUMNS + _metafield_columns(cfg)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()

    used_handles: dict[str, int] = {}

    for product in launch.products:
        data = product.get_data()
        prod = data.get("product", {}) or {}
        items = data.get("items", []) or []

        title = _flat(prod.get(cfg["title_field"])).strip()
        base_handle = slugify(title)
        n = used_handles.get(base_handle, 0)
        used_handles[base_handle] = n + 1
        handle = base_handle if n == 0 else f"{base_handle}-{n + 1}"

        # ---- build variants (each = a dict of Option name -> value, + sku/price) ----
        variants = []
        for it in items:
            base_sku = str(it.get(cfg["sku_field"], "") or "").strip()
            price = _num(it.get(cfg["price_field"]))
            compare = _num(it.get(cfg["compare_at_field"]))
            explode_vals = _as_list(it.get(explode["field"])) if explode else []
            explode_vals = [str(v).strip() for v in explode_vals] or [""]
            for ev in explode_vals:
                opt_values = {}
                for o in options:
                    opt_values[o["name"]] = ev if o is explode else _opt_value(o, it, prod)
                sku = f"{base_sku}-{ev}" if (base_sku and ev and cfg["append_option_to_sku"]) else base_sku
                variants.append({"opts": opt_values, "sku": sku, "price": price, "compare": compare})
        if not variants:
            variants = [{"opts": {o["name"]: "" for o in options}, "sku": "", "price": "", "compare": ""}]

        # which configured options actually carry values -> become Option1..3
        used_opts = [o for o in options if any(v["opts"].get(o["name"], "") for v in variants)]
        if not used_opts:
            used_opts = [{"name": "Title", "_default": "Default Title"}]

        # ---- product-level values (first row only) ----
        body = _body_html(prod.get(cfg["body_field"], ""))
        vendor = _flat(prod.get(cfg["vendor_field"])).strip()
        ptype = _flat(prod.get(cfg["type_field"])).strip()
        tags = ", ".join(dict.fromkeys(
            t for key in cfg["tags_fields"] for t in
            [x.strip() for x in _as_list(prod.get(key))] if t))
        images = [str(u).strip() for u in _as_list(prod.get(cfg["images_field"])) if str(u).strip()]
        published = "TRUE" if cfg["published"] else "FALSE"
        metafield_vals = {
            _metafield_header_for(cfg, m): _flat(prod.get(m["field"]))
            for m in cfg["metafields"]
        }

        for i, v in enumerate(variants):
            row = {c: "" for c in columns}
            row["Handle"] = handle
            for oi, o in enumerate(used_opts[:3], start=1):
                row[f"Option{oi} Name"] = o["name"]
                row[f"Option{oi} Value"] = o.get("_default") or v["opts"].get(o["name"], "") or "Default"
            row["Variant SKU"] = v["sku"]
            row["Variant Inventory Tracker"] = "shopify"
            row["Variant Inventory Policy"] = "deny"
            row["Variant Fulfillment Service"] = "manual"
            row["Variant Price"] = v["price"]
            row["Variant Compare At Price"] = v["compare"]
            row["Variant Requires Shipping"] = "TRUE"
            row["Variant Taxable"] = "TRUE"
            row["Variant Weight Unit"] = cfg["weight_unit"]
            if i == 0:
                row["Title"] = title
                row["Body (HTML)"] = body
                row["Vendor"] = vendor
                row["Type"] = ptype
                row["Tags"] = tags
                row["Published"] = published
                row["Gift Card"] = "FALSE"
                row["SEO Title"] = title
                row["SEO Description"] = (_flat(prod.get(cfg["body_field"])) or "")[:320]
                row["Status"] = cfg["status"]
                for col, val in metafield_vals.items():
                    row[col] = val
                if images:
                    row["Image Src"] = images[0]
                    row["Image Position"] = "1"
                    row["Image Alt Text"] = title
            writer.writerow(row)

        for pos, img in enumerate(images[1:], start=2):
            row = {c: "" for c in columns}
            row["Handle"] = handle
            row["Image Src"] = img
            row["Image Position"] = str(pos)
            writer.writerow(row)

    return buf.getvalue()


def _metafield_header_for(cfg: dict, m: dict) -> str:
    return cfg["metafield_header"].format(
        name=m.get("name", m["key"]),
        namespace=m.get("namespace", cfg["metafield_namespace"]),
        key=m["key"], type=m.get("type", "single_line_text_field"))
