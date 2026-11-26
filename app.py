"""Flask web interface for graphe-verification-framework.

Provides a simple web UI (/) and JSON API (/api/verify) where users can submit a
scripture reference in English or Greek and receive a fail-closed, citation-enforced
readout validated against `schema/analysis.json`.
"""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, render_template, request
from jsonschema import ValidationError

from validate import VerificationEngineError, normalize_nfc, verify_passage


def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__, template_folder="templates")
    app.config["JSON_AS_ASCII"] = False

    @app.get("/")
    def index() -> str:
        """Render the reference input form and optional initial readout."""
        raw_query = request.args.get("ref", "")
        clean_query = normalize_nfc(raw_query).strip() if raw_query else ""
        analysis: dict[str, Any] | None = None
        error_message: str | None = None

        if clean_query:
            try:
                analysis = verify_passage(clean_query)
            except (VerificationEngineError, ValidationError, ValueError) as exc:
                error_message = str(exc)

        return render_template(
            "index.html",
            query=clean_query,
            analysis=analysis,
            error_message=error_message,
        )

    @app.post("/verify")
    def verify_form() -> str:
        """Handle form submissions from the web interface and display the readout."""
        raw_query = request.form.get("reference", "")
        clean_query = normalize_nfc(raw_query).strip()
        analysis: dict[str, Any] | None = None
        error_message: str | None = None

        try:
            analysis = verify_passage(clean_query)
        except (VerificationEngineError, ValidationError, ValueError) as exc:
            error_message = str(exc)

        return render_template(
            "index.html",
            query=clean_query,
            analysis=analysis,
            error_message=error_message,
        )

    @app.get("/api/verify")
    def api_verify_get():
        """JSON endpoint supporting GET /api/verify?ref=... for local inspection."""
        raw_query = request.args.get("ref", "")
        clean_query = normalize_nfc(raw_query).strip()
        try:
            result = verify_passage(clean_query)
            return jsonify(result), 200
        except (VerificationEngineError, ValidationError, ValueError) as exc:
            return jsonify({"error": str(exc), "overall_verdict": "FAIL"}), 400

    @app.post("/api/verify")
    def api_verify_post():
        """JSON endpoint supporting POST /api/verify with JSON or form payload."""
        data = request.get_json(silent=True)
        if isinstance(data, dict) and "reference" in data:
            raw_query = str(data["reference"])
        else:
            raw_query = request.form.get("reference", "") or request.args.get("ref", "")

        clean_query = normalize_nfc(raw_query).strip()
        try:
            result = verify_passage(clean_query)
            return jsonify(result), 200
        except (VerificationEngineError, ValidationError, ValueError) as exc:
            return jsonify({"error": str(exc), "overall_verdict": "FAIL"}), 400

    return app


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
