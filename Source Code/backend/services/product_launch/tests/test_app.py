"""Basic smoke tests for the core flows.

Run:  python -m pytest    (or)    python tests/test_app.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app          # noqa: E402
from app.config import Config       # noqa: E402
from app.extensions import db       # noqa: E402
from app.models import Launch       # noqa: E402


def make_app():
    tmp = tempfile.mkdtemp()

    class T(Config):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(tmp, 't.db')}"
        SECRET_KEY = "test"
        ADMIN_USERNAME = "admin"
        ADMIN_PASSWORD = "pw"
        ADMIN_PASSWORD_HASH = None
        TESTING = True

    return create_app(T)


def admin_login(client):
    # fetch a page to establish a session + csrf, then log in
    client.get("/admin/login")
    return client.post("/admin/login", data={"username": "admin", "password": "pw"},
                       follow_redirects=True)


def csrf_from(client):
    with client.session_transaction() as sess:
        return sess.get("csrf_token", "")


def test_launch_lifecycle():
    app = make_app()
    client = app.test_client()

    # admin creates a launch
    admin_login(client)
    token_csrf = csrf_from(client)
    r = client.post("/admin/api/launches", json={"brand_name": "Acme"},
                    headers={"X-CSRF-Token": token_csrf})
    assert r.status_code == 201, r.data
    token = r.get_json()["token"]

    # public GET works with the token
    r = client.get(f"/api/launch/{token}")
    assert r.status_code == 200
    assert r.get_json()["launch"]["brand_name"] == "Acme"

    # add a product (token-gated, no admin needed) — two-level shape
    pub = app.test_client()
    r = pub.post(f"/api/launch/{token}/products",
                 json={"data": {
                     "product": {"title": "Shirt", "product_type": "Formals",
                                 "description": "A shirt."},
                     "items": [{"item": "Shirt/Pants", "sku": "S1", "price": "100",
                                "sizes": ["S", "M"], "fabric": ["Cotton"]}],
                 }})
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["summary"]["total"] == 1
    pid = payload["created_pid"]
    # all required product + item fields present -> complete
    prod = payload["products"][0]
    assert prod["validation"]["complete"] is True, prod["validation"]

    # duplicate SKU (item level) is flagged, not blocked
    pub.post(f"/api/launch/{token}/products",
             json={"data": {"product": {"title": "Shirt2"},
                            "items": [{"item": "Kurta", "sku": "S1", "price": "50",
                                       "sizes": ["S"]}]}})
    r = pub.get(f"/api/launch/{token}")
    assert r.get_json()["summary"]["duplicate_skus"]

    # invalid number on an item is flagged
    r = pub.put(f"/api/launch/{token}/products/{pid}",
                json={"data": {"product": {"title": "Shirt", "product_type": "Formals",
                                           "description": "A shirt."},
                               "items": [{"item": "Shirt/Pants", "sku": "S1",
                                          "price": "abc", "sizes": ["S"]}]}})
    assert "price" in r.get_json()["products"][0]["validation"]["item_errors"][0]

    # another client's random token can't read this data
    assert pub.get("/api/launch/does-not-exist").status_code == 404


def test_csv_export_requires_admin_and_has_filename():
    app = make_app()
    client = app.test_client()
    admin_login(client)
    csrf = csrf_from(client)
    token = client.post("/admin/api/launches", json={"brand_name": "Brand X"},
                        headers={"X-CSRF-Token": csrf}).get_json()["token"]
    client.post(f"/api/launch/{token}/products",
                json={"data": {"product": {"title": "P1"},
                               "items": [{"item": "2pc", "sku": "K1",
                                          "sizes": ["S", "M"],
                                          "fabric": ["Silk", "Cotton"]}]}})

    # logged-out client cannot export
    anon = app.test_client()
    assert anon.get(f"/admin/launch/{token}/export.csv").status_code in (302, 401)

    # admin can, filename carries brand + token, multi-values joined
    r = client.get(f"/admin/launch/{token}/export.csv")
    assert r.status_code == 200
    assert f"Brand_X_Product_Launch_{token}.csv" in r.headers["Content-Disposition"]
    body = r.get_data(as_text=True)
    assert "S | M" in body and "Silk | Cotton" in body


def test_shopify_export_variant_rows():
    app = make_app()
    client = app.test_client()
    admin_login(client)
    csrf = csrf_from(client)
    token = client.post("/admin/api/launches", json={"brand_name": "Studio Y"},
                        headers={"X-CSRF-Token": csrf}).get_json()["token"]

    # one product, two item-sets, 4 sizes each -> 8 variant rows + product row info
    client.post(f"/api/launch/{token}/products", json={"data": {
        "product": {"title": "Biscuit Fold", "product_type": "Fusion Wear",
                    "brand": "Studio Y", "description": "Line one.\nLine two.",
                    "collection": "Nuance", "color": "Beige",
                    "images": ["https://x/1.jpg", "https://x/2.jpg"]},
        "items": [
            {"item": "Shirt/Pants", "sku": "BF-2PC", "price": "32000",
             "compare_at_price": "38000", "fabric": ["Georgette", "Russian Silk"],
             "sizes": ["S", "M", "L", "XL"]},
            {"item": "Shirt/Pants/Dupatta", "sku": "BF-3PC", "price": "42000",
             "fabric": ["Georgette", "Russian Silk", "Pure Organza"],
             "sizes": ["S", "M", "L", "XL"]},
        ],
    }})

    r = client.get(f"/admin/launch/{token}/shopify.csv")
    assert r.status_code == 200
    assert "Studio_Y_Shopify_Import_" in r.headers["Content-Disposition"]
    text = r.get_data(as_text=True).lstrip("﻿")
    header = text.splitlines()[0]
    assert header.startswith("Handle,Title,Body (HTML),Vendor")
    # metafield column present for Color
    assert "Color (product.metafields.custom.color)" in header

    import csv as _csv
    rows = list(_csv.DictReader(text.splitlines()))
    # 8 variant rows + 1 extra image row = 9
    assert len(rows) == 9, len(rows)
    variant_rows = [row for row in rows if row["Variant SKU"]]
    assert len(variant_rows) == 8
    # per-size SKU generated
    skus = {row["Variant SKU"] for row in variant_rows}
    assert "BF-2PC-M" in skus and "BF-3PC-XL" in skus
    # options: Item / Fabric / Size
    assert variant_rows[0]["Option1 Name"] == "Item"
    assert variant_rows[0]["Option2 Name"] == "Fabric"
    assert variant_rows[0]["Option3 Name"] == "Size"
    assert variant_rows[0]["Option1 Value"] == "Shirt/Pants"
    assert variant_rows[0]["Option2 Value"] == "Georgette / Russian Silk"
    # mapping: Vendor = collection, Type = product_type
    assert rows[0]["Vendor"] == "Nuance"
    assert rows[0]["Type"] == "Fusion Wear"
    # color is a metafield on the first row only
    assert rows[0]["Color (product.metafields.custom.color)"] == "Beige"
    assert rows[1]["Color (product.metafields.custom.color)"] == ""
    # product-level info only on the first row; same Handle throughout
    assert rows[0]["Title"] == "Biscuit Fold"
    assert rows[1]["Title"] == ""
    assert len({row["Handle"] for row in rows}) == 1
    assert rows[0]["Body (HTML)"].startswith("<p>Line one.</p>")
    # extra image row present
    assert any(row["Image Src"] == "https://x/2.jpg" and not row["Variant SKU"] for row in rows)


def test_admin_csrf_enforced():
    app = make_app()
    client = app.test_client()
    admin_login(client)
    # missing CSRF header on a state-changing admin call -> 403
    r = client.post("/admin/api/launches", json={"brand_name": "NoCSRF"})
    assert r.status_code == 403


if __name__ == "__main__":
    test_launch_lifecycle()
    test_csv_export_requires_admin_and_has_filename()
    test_shopify_export_variant_rows()
    test_admin_csrf_enforced()
    print("All tests passed.")
