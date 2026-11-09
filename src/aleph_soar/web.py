"""Scaffold routes; business APIs are specified separately in the contract."""

from flask import Blueprint, jsonify, render_template

blueprint = Blueprint("workspace", __name__)


@blueprint.get("/")
def workspace():
    return render_template("workspace.html")


@blueprint.get("/api/v1/health")
def health():
    return jsonify(
        success=True,
        data={"service": "aleph-soar", "status": "ok", "stage": "scaffold"},
    )
