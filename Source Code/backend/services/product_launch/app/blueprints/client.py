"""Public, client-facing pages.

The client never logs in. They open ``/launch/<token>`` and the page's
JavaScript talks to the token-gated API. A friendly landing page lives at ``/``.
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template

from ..extensions import db
from ..models import Launch

bp = Blueprint("client", __name__)


@bp.get("/")
def index():
    return render_template("landing.html")


@bp.get("/launch/<token>")
def launch(token):
    exists = db.session.execute(
        db.select(Launch.id).filter_by(token=token)
    ).scalar_one_or_none()
    if exists is None:
        abort(404)
    # The page is a thin shell; all data is loaded via the API using the token.
    return render_template("client.html", token=token)


@bp.get("/healthz")
def healthz():
    return {"status": "ok"}
