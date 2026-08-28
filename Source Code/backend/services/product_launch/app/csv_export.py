"""CSV generation for a launch's products (two-level model).

* Each **item-set** is one row; a product with several item-sets (e.g. 2-piece
  and 3-piece) produces several rows, with the product-level fields repeated.
* Each configured field is its own column (product fields, then item fields).
* Multi-value fields (sizes, fabrics, images, ...) are joined with a single,
  consistent delimiter (configurable via ``MULTI_VALUE_DELIMITER``).
* Exact values entered by the client are preserved; nothing is dropped.
"""
from __future__ import annotations

import csv
import io
import re

from flask import current_app

from . import fields as F
from . import validation


def safe_filename_part(text: str) -> str:
    text = (text or "").strip() or "Brand"
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "Brand"


def export_filename(launch) -> str:
    brand = safe_filename_part(launch.brand_name)
    return f"{brand}_Product_Launch_{launch.token}.csv"


def _cell(field: dict, value, delimiter: str) -> str:
    if F.is_multi(field) and isinstance(value, list):
        return delimiter.join(str(v) for v in value)
    return "" if value is None else str(value)


def build_csv(launch) -> str:
    delimiter = current_app.config["MULTI_VALUE_DELIMITER"]
    pfields = F.product_fields()
    ifields = F.item_fields()
    dup = validation.duplicate_sku_values(launch.products)

    header = (
        ["Launch ID", "Launch Brand"]
        + [f["label"] for f in pfields]
        + [f"{F.item_label()} #"]
        + [f["label"] for f in ifields]
        + ["Completion", "Missing Fields"]
    )

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)

    for product in launch.products:
        data = product.get_data()
        prod = data.get("product", {}) or {}
        items = data.get("items", []) or []

        summary = validation.evaluate_product(data)
        validation.apply_duplicates(summary, data, dup)
        completion = "Complete" if summary["complete"] else "Incomplete"
        missing = delimiter.join(summary["missing"])

        prod_cells = [_cell(f, prod.get(f["key"]), delimiter) for f in pfields]

        if items:
            for i, it in enumerate(items):
                item_cells = [_cell(f, it.get(f["key"]), delimiter) for f in ifields]
                writer.writerow(
                    [launch.token, launch.brand_name] + prod_cells
                    + [str(i + 1)] + item_cells + [completion, missing]
                )
        else:
            writer.writerow(
                [launch.token, launch.brand_name] + prod_cells
                + [""] + [""] * len(ifields) + [completion, missing]
            )

    return buf.getvalue()
