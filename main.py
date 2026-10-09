"""
main.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.

Application desktop entry point:
1. Initialises the database
2. Starts the Flask server in a background thread
3. Starts the ngrok tunnel in a daemon thread
4. Opens a pywebview desktop window pointing at localhost:5000
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup (early, before any imports that log)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Bootstrap DB
# ---------------------------------------------------------------------------
import database as db

db.init_db()
log.info("Database ready at %s", db.DB_PATH)

# ---------------------------------------------------------------------------
# Start Flask server in a background daemon thread
# ---------------------------------------------------------------------------
import app as flask_app

_PORT = 5000
_SERVER_READY = threading.Event()


def _flask_thread():
    from waitress import serve  # type: ignore

    log.info("Starting Flask via Waitress on port %d …", _PORT)
    _SERVER_READY.set()
    serve(flask_app.app, host="127.0.0.1", port=_PORT, threads=8)


_t_flask = threading.Thread(target=_flask_thread, daemon=True, name="flask-server")
_t_flask.start()

# ---------------------------------------------------------------------------
# Start background services: ngrok tunnel & headless WhatsApp bridge
# ---------------------------------------------------------------------------
import tunnel
import wa_process

auth_token = db.get_setting("ngrok_auth_token")
tunnel.start_tunnel(port=_PORT, auth_token=auth_token)
wa_process.start_wa_bridge()

# ---------------------------------------------------------------------------
# Wait for Flask to be ready (max 10 s)
# ---------------------------------------------------------------------------
_SERVER_READY.wait(timeout=10)
time.sleep(0.5)  # small grace period for the socket to bind

# ---------------------------------------------------------------------------
# Launch PyWebView desktop window
# ---------------------------------------------------------------------------
def _start_webview():
    try:
        import webview  # type: ignore

        log.info("Opening desktop window via pywebview …")
        window = webview.create_window(
            title="Haven Stays — Property Management",
            url=f"http://127.0.0.1:{_PORT}",
            width=1400,
            height=900,
            min_size=(1024, 700),
            resizable=True,
            frameless=False,
            easy_drag=False,
        )
        webview.start(
            debug=False,
            private_mode=True,
        )
    except ImportError:
        log.warning(
            "pywebview not installed — opening in system browser instead.\n"
            "Install with: pip install pywebview"
        )
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{_PORT}")
        # Keep main thread alive so Flask keeps running
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


_start_webview()

# Cleanup on window close
tunnel.stop_tunnel()
wa_process.stop_wa_bridge()
log.info("Haven Stays shut down cleanly.")
