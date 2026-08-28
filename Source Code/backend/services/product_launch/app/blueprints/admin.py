"""Admin (internal) pages and admin-only API.

Protected by session login. Handles: dashboard listing every launch, creating a
new launch (and thus a shareable client link), reviewing/editing a launch
(reusing the same dynamic form in admin mode), status changes, launch deletion,
and CSV export.
"""
from __future__ import annotations

from flask import (
    Blueprint, Response, abort, current_app, jsonify, redirect,
    render_template, request, url_for,
)

from .. import auth
from ..csv_export import build_csv, export_filename
from .. import shopify_export
from ..extensions import db
from ..models import Launch, make_token
from .. import validation

bp = Blueprint("admin", __name__, url_prefix="/admin")

VALID_STATUSES = ["Draft", "Submitted", "Under Review", "Approved", "Rejected"]


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth.verify_credentials(username, password):
            auth.login_admin()
            nxt = request.args.get("next") or url_for("admin.dashboard")
            if not nxt.startswith("/"):  # open-redirect guard
                nxt = url_for("admin.dashboard")
            return redirect(nxt)
        error = "Incorrect username or password."
    return render_template("admin_login.html", error=error)


@bp.get("/logout")
def logout():
    auth.logout_admin()
    return redirect(url_for("admin.login"))


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #
@bp.get("/")
@auth.admin_required
def dashboard():
    launches = db.session.execute(
        db.select(Launch).order_by(Launch.updated_at.desc())
    ).scalars().all()

    rows = []
    for ln in launches:
        dup_skus = validation.duplicate_sku_values(ln.products)
        complete = 0
        for p in ln.products:
            summary = validation.evaluate_product(p.get_data())
            validation.apply_duplicates(summary, p.get_data(), dup_skus)
            if summary["complete"]:
                complete += 1
        rows.append({
            "launch": ln,
            "complete": complete,
            "total": len(ln.products),
        })
    return render_template("admin_list.html", rows=rows, statuses=VALID_STATUSES)


@bp.get("/launch/<token>")
@auth.admin_required
def review(token):
    launch = db.session.execute(
        db.select(Launch).filter_by(token=token)
    ).scalar_one_or_none()
    if launch is None:
        abort(404)
    return render_template(
        "admin_launch.html", token=token, launch=launch, statuses=VALID_STATUSES
    )


# --------------------------------------------------------------------------- #
# admin API (session + CSRF protected)
# --------------------------------------------------------------------------- #
@bp.post("/api/launches")
@auth.admin_api_required
def create_launch():
    body = request.get_json(silent=True) or {}
    launch = Launch(
        token=make_token(current_app.config["TOKEN_BYTES"]),
        brand_name=(body.get("brand_name") or "").strip(),
        contact_name=(body.get("contact_name") or "").strip(),
        contact_email=(body.get("contact_email") or "").strip(),
    )
    db.session.add(launch)
    db.session.commit()
    return jsonify({
        "token": launch.token,
        "client_url": url_for("client.launch", token=launch.token, _external=True),
        "review_url": url_for("admin.review", token=launch.token, _external=True),
    }), 201


@bp.put("/api/launch/<token>/status")
@auth.admin_api_required
def set_status(token):
    launch = db.session.execute(
        db.select(Launch).filter_by(token=token)
    ).scalar_one_or_none()
    if launch is None:
        abort(404)
    status = (request.get_json(silent=True) or {}).get("status", "")
    if status not in VALID_STATUSES:
        return jsonify({"error": "Invalid status."}), 400
    launch.status = status
    launch.touch()
    db.session.commit()
    return jsonify({"status": launch.status})


@bp.delete("/api/launch/<token>")
@auth.admin_api_required
def delete_launch(token):
    launch = db.session.execute(
        db.select(Launch).filter_by(token=token)
    ).scalar_one_or_none()
    if launch is None:
        abort(404)
    db.session.delete(launch)
    db.session.commit()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------- #
# CSV export (admin only)
# --------------------------------------------------------------------------- #
@bp.get("/launch/<token>/export.csv")
@auth.admin_required
def export_csv(token):
    launch = db.session.execute(
        db.select(Launch).filter_by(token=token)
    ).scalar_one_or_none()
    if launch is None:
        abort(404)
    csv_text = build_csv(launch)
    # UTF-8 BOM so Excel opens non-ASCII (é, ü, ₨) correctly.
    body = "﻿" + csv_text
    return Response(
        body,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{export_filename(launch)}"'
        },
    )


@bp.get("/launch/<token>/shopify.csv")
@auth.admin_required
def export_shopify_csv(token):
    launch = db.session.execute(
        db.select(Launch).filter_by(token=token)
    ).scalar_one_or_none()
    if launch is None:
        abort(404)
    body = "﻿" + shopify_export.build_csv(launch)
    return Response(
        body,
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="{shopify_export.export_filename(launch)}"'
        },
    )
