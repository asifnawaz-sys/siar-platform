"""Database models.

Design notes
------------
* A **Launch** is one product-launch request for a single brand/client. It owns
  a secure, unguessable ``token`` that forms the shareable URL. Internal integer
  primary keys are never exposed to the outside world.
* A **Product** belongs to exactly one Launch. Its field values are stored as a
  JSON blob (``data``) so that the set of product fields can be reconfigured in
  ``field_config.json`` without any database migration.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from .extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_token(nbytes: int = 9) -> str:
    """URL-safe, cryptographically-random token (e.g. 'x7Kd9AbQ_-')."""
    return secrets.token_urlsafe(nbytes)


class Launch(db.Model):
    __tablename__ = "launches"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True,
                      default=lambda: make_token(9))
    brand_name = db.Column(db.String(255), nullable=False, default="")
    contact_name = db.Column(db.String(255), nullable=False, default="")
    contact_email = db.Column(db.String(255), nullable=False, default="")
    # Draft / Submitted / Under Review / Approved / Rejected (future workflow).
    status = db.Column(db.String(32), nullable=False, default="Draft")
    notes = db.Column(db.Text, nullable=False, default="")

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    products = db.relationship(
        "Product",
        backref="launch",
        cascade="all, delete-orphan",
        order_by="Product.position",
        lazy="selectin",
    )

    def touch(self) -> None:
        self.updated_at = utcnow()

    def to_dict(self, include_products: bool = False) -> dict:
        data = {
            "token": self.token,
            "brand_name": self.brand_name,
            "contact_name": self.contact_name,
            "contact_email": self.contact_email,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "product_count": len(self.products),
        }
        if include_products:
            data["products"] = [p.to_dict() for p in self.products]
        return data


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    # Public, unguessable id used in URLs/JS so internal ids stay hidden.
    pid = db.Column(db.String(64), unique=True, nullable=False, index=True,
                    default=lambda: make_token(8))
    launch_id = db.Column(
        db.Integer, db.ForeignKey("launches.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    position = db.Column(db.Integer, nullable=False, default=0)
    # JSON object: { field_key: value }. Multi-value fields hold JSON arrays.
    data = db.Column(db.Text, nullable=False, default="{}")

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # --- convenience accessors for the JSON blob ---
    def get_data(self) -> dict:
        try:
            return json.loads(self.data) if self.data else {}
        except (ValueError, TypeError):
            return {}

    def set_data(self, values: dict) -> None:
        self.data = json.dumps(values, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "position": self.position,
            "data": self.get_data(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
