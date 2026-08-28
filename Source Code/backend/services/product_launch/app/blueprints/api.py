"""JSON API for launches and products.

Access model
------------
All ``/api/launch/<token>/...`` endpoints are gated purely by the secret launch
token in the URL. Whoever holds the link (the client, or our admin who created
it) may read and edit that launch — and *only* that launch. There is no shared,
ambient session here, so one client can never reach another client's data, and
these endpoints are not exposed to CSRF.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from ..extensions import db
from ..fields import get_config
from ..models import Launch, Product, utcnow
from .. import validation

bp = Blueprint("api", __name__, url_prefix="/api")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _get_launch_or_404(token: str) -> Launch:
    launch = db.session.execute(
        db.select(Launch).filter_by(token=token)
    ).scalar_one_or_none()
    if launch is None:
        abort(404)
    return launch


def _get_product_or_404(launch: Launch, pid: str) -> Product:
    for p in launch.products:
        if p.pid == pid:
            return p
    abort(404)


def _launch_payload(launch: Launch) -> dict:
    dup_skus = validation.duplicate_sku_values(launch.products)

    products = []
    complete_count = 0
    for p in launch.products:
        data = p.get_data()
        summary = validation.evaluate_product(data)
        has_dup = validation.apply_duplicates(summary, data, dup_skus)
        if summary["complete"]:
            complete_count += 1
        item = p.to_dict()
        item["validation"] = summary
        item["duplicate_sku"] = has_dup
        products.append(item)

    return {
        "launch": launch.to_dict(),
        "config": get_config(),
        "products": products,
        "summary": {
            "total": len(products),
            "complete": complete_count,
            "incomplete": len(products) - complete_count,
            "duplicate_skus": sorted(dup_skus),
        },
    }


def _json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
@bp.get("/config")
def config():
    return jsonify(get_config())


# --------------------------------------------------------------------------- #
# launch
# --------------------------------------------------------------------------- #
@bp.get("/launch/<token>")
def get_launch(token):
    launch = _get_launch_or_404(token)
    return jsonify(_launch_payload(launch))


@bp.put("/launch/<token>")
def update_launch(token):
    launch = _get_launch_or_404(token)
    body = _json_body()
    for attr in ("brand_name", "contact_name", "contact_email", "notes"):
        if attr in body and isinstance(body[attr], str):
            setattr(launch, attr, body[attr].strip())
    launch.touch()
    db.session.commit()
    return jsonify(_launch_payload(launch))


@bp.post("/launch/<token>/submit")
def submit_launch(token):
    launch = _get_launch_or_404(token)
    launch.status = "Submitted"
    launch.touch()
    db.session.commit()
    return jsonify(_launch_payload(launch))


# --------------------------------------------------------------------------- #
# products
# --------------------------------------------------------------------------- #
@bp.post("/launch/<token>/products")
def create_product(token):
    launch = _get_launch_or_404(token)
    data = validation.clean_product(_json_body().get("data", {}))

    next_pos = (max((p.position for p in launch.products), default=-1)) + 1
    product = Product(launch_id=launch.id, position=next_pos)
    product.set_data(data)
    db.session.add(product)
    launch.touch()
    db.session.commit()

    payload = _launch_payload(launch)
    payload["created_pid"] = product.pid
    return jsonify(payload), 201


@bp.put("/launch/<token>/products/<pid>")
def update_product(token, pid):
    launch = _get_launch_or_404(token)
    product = _get_product_or_404(launch, pid)
    product.set_data(validation.clean_product(_json_body().get("data", {})))
    product.updated_at = utcnow()
    launch.touch()
    db.session.commit()
    return jsonify(_launch_payload(launch))


@bp.delete("/launch/<token>/products/<pid>")
def delete_product(token, pid):
    launch = _get_launch_or_404(token)
    product = _get_product_or_404(launch, pid)
    db.session.delete(product)
    launch.touch()
    db.session.commit()
    return jsonify(_launch_payload(launch))
