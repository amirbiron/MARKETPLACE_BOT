"""
Tiny Flask HTTP server for Render health checks (and optional admin loglevel).

Routes:
- GET /          -> basic status
- GET /health    -> health status
- POST /admin/loglevel?token=...&level=INFO|DEBUG|WARNING|ERROR|CRITICAL
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class _LockLike(Protocol):
    @property
    def is_acquired(self) -> bool: ...

    @property
    def settings(self): ...


def _set_global_loglevel(level_name: str) -> bool:
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        return False

    logging.getLogger().setLevel(level)
    for handler in logging.getLogger().handlers:
        handler.setLevel(level)
    return True


def start_health_server(lock: Optional[_LockLike] = None) -> None:
    """
    Start Flask server in a daemon thread, if PORT is set.
    """
    port_raw = os.getenv("PORT")
    if not port_raw:
        return

    try:
        port = int(port_raw)
    except ValueError:
        logger.warning(f"Invalid PORT={port_raw}; skipping health server")
        return

    # Local import so Flask is optional outside Render.
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.get("/")
    def root():
        return jsonify(
            {
                "ok": True,
                "lock_acquired": bool(getattr(lock, "is_acquired", False)),
                "service_id": getattr(getattr(lock, "settings", None), "service_id", None),
                "instance_id": getattr(getattr(lock, "settings", None), "instance_id", None),
            }
        )

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "lock_acquired": bool(getattr(lock, "is_acquired", False)),
            }
        )

    @app.post("/admin/loglevel")
    def admin_loglevel():
        token = request.args.get("token") or request.headers.get("X-Admin-Token")
        expected = os.getenv("LOG_ADMIN_TOKEN")
        if expected and token != expected:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

        level = request.args.get("level") or (request.json.get("level") if request.is_json else None)
        if not level:
            return jsonify({"ok": False, "error": "missing level"}), 400

        if not _set_global_loglevel(level):
            return jsonify({"ok": False, "error": "invalid level"}), 400

        return jsonify({"ok": True, "level": level.upper()})

    def _run():
        # No reloader; daemon thread.
        logger.info(f"Starting health server on 0.0.0.0:{port}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    threading.Thread(target=_run, name="health-server", daemon=True).start()

