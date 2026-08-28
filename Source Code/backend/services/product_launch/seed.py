"""Create sample/test data.

Usage:  python seed.py
Prints the client link and admin review link for a demo launch so you can try
the app immediately. Safe to run multiple times (it adds a fresh demo launch).
"""
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models import Launch, Product


DEMO_PRODUCTS = [
    {
        "product": {
            "title": "Biscuit Fold", "product_type": "Fusion Wear", "brand": "Studio SY",
            "category": "Womenswear", "subcategory": "3-Piece Suit",
            "collection": "Nuance Edit IV",
            "description": ("Softly structured and fluid in motion, Biscuit Fold is crafted in "
                            "heavy georgette layered over luminous Russian silk."),
            "color": "Warm Biscuit Beige", "length": "28 in (top) / 42 in (bottom)",
            "care": "Dry Clean Only",
            "images": ["https://example.com/biscuit-fold-1.jpg",
                       "https://example.com/biscuit-fold-2.jpg"],
        },
        "items": [
            {
                "item": "Shirt/Pants", "sku": "BISCUITFOLD-FW-2PC",
                "fabric": ["Georgette", "Russian Silk"],
                "price": "32000", "compare_at_price": "38000",
                "sizes": ["S", "M", "L", "XL"],
            },
            {
                "item": "Shirt/Pants/Dupatta", "sku": "BISCUITFOLD-FW-3PC",
                "fabric": ["Georgette", "Russian Silk", "Pure Organza"],
                "price": "42000", "compare_at_price": "",
                "sizes": ["S", "M", "L", "XL"],
            },
        ],
    },
    {
        # Intentionally incomplete, to demonstrate the "missing fields" badges.
        "product": {"title": "Ivory Whisper", "product_type": "", "description": ""},
        "items": [],
    },
]


def main():
    app = create_app()
    with app.app_context():
        launch = Launch(
            brand_name="Studio SY",
            contact_name="Sara Yusuf",
            contact_email="sara@studiosy.example",
            status="Draft",
        )
        db.session.add(launch)
        db.session.flush()

        for i, data in enumerate(DEMO_PRODUCTS):
            p = Product(launch_id=launch.id, position=i)
            p.set_data(data)
            db.session.add(p)

        db.session.commit()

        print("\n=== Demo launch created ===")
        print(f"Brand       : {launch.brand_name}")
        print(f"Token       : {launch.token}")
        print(f"Products    : {len(DEMO_PRODUCTS)}")
        print(f"Client link : http://127.0.0.1:5000/launch/{launch.token}")
        print(f"Admin review: http://127.0.0.1:5000/admin/launch/{launch.token}")
        print(f"Admin login : http://127.0.0.1:5000/admin  "
              f"(user 'admin', password from .env / default 'changeme')\n")


if __name__ == "__main__":
    main()
