"""Loading and helpers for the configurable field definitions.

The field configuration is the single source of truth for what a product looks
like. A product has two levels:

* ``product_fields`` — entered once per product (title, description, images…)
* ``item_fields``    — repeated for each *item-set* (a priced configuration such
  as a 2-piece vs 3-piece option), each with its own item name, fabric, price
  and sizes.

Both the backend (validation, CSV export) and the frontend (dynamic form
rendering) consume this file, so fields can be added, removed, or reworded by
editing ``field_config.json`` alone.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache

from flask import current_app

MULTI_VALUE_TYPES = {"tags", "multiselect"}


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _cached(path: str, mtime: float) -> dict:
    # mtime is part of the cache key so edits to the file are picked up.
    return _load(path)


def get_config() -> dict:
    path = current_app.config["FIELD_CONFIG_PATH"]
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return _cached(path, mtime)


def product_fields() -> list[dict]:
    return get_config().get("product_fields", [])


def item_fields() -> list[dict]:
    return get_config().get("item_fields", [])


def min_items() -> int:
    return int(get_config().get("min_items", 1))


def item_label() -> str:
    return get_config().get("item_label", "Item-set")


def is_multi(field: dict) -> bool:
    return field.get("type") in MULTI_VALUE_TYPES


def required(fields: list[dict]) -> list[str]:
    return [f["key"] for f in fields if f.get("required")]


def unique_item_keys() -> list[str]:
    return [f["key"] for f in item_fields() if f.get("unique")]
