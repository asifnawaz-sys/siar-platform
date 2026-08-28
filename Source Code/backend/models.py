from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Variant:
    sku: str = ""
    option1: str = ""
    option2: str = ""
    option3: str = ""
    price: str = ""
    compare_at_price: str = ""
    barcode: str = ""
    weight_grams: Optional[float] = None
    inventory_quantity: Optional[int] = None
    inventory_policy: str = "deny"
    inventory_tracker: str = "shopify"
    image_src: str = ""

@dataclass
class Product:
    handle: str = ""
    title: str = ""
    body_html: str = ""
    vendor: str = ""
    product_type: str = ""
    category: str = ""
    tags: str = ""
    published: bool = True
    status: str = "active"
    images: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    source_url: str = ""
    seo_title: str = ""
    seo_description: str = ""
