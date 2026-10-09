"""
tunnel.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.

Manages the background ngrok / localtunnel process.
Starts the tunnel in a daemon thread, polls for the public URL,
and exposes it via a thread-safe variable read by the Flask app.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State (shared across threads, written once after tunnel starts)
# ---------------------------------------------------------------------------
_public_url: Optional[str] = None
_tunnel_process: Optional[subprocess.Popen] = None
_lock = threading.Lock()


def get_public_url() -> Optional[str]:
    with _lock:
        return _public_url


def _set_public_url(url: str) -> None:
    global _public_url
    with _lock:
        _public_url = url
    log.info("Tunnel public URL: %s", url)


# ---------------------------------------------------------------------------
# Locate ngrok binary (bundled inside PyInstaller package or on PATH)
# ---------------------------------------------------------------------------
def _ngrok_path() -> str:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "bin",
            exe_dir / "_internal" / "bin",
            exe_dir / "_internal",
            exe_dir,
        ])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.extend([
                Path(meipass) / "bin",
                Path(meipass),
            ])

    base = Path(__file__).parent
    candidates.extend([
        base / "bin",
        base,
        Path.home() / "AppData" / "Local" / "ngrok",
    ])

    for folder in candidates:
        for name in ("ngrok.exe", "ngrok"):
            candidate = folder / name
            if candidate.exists() and candidate.is_file():
                log.info("Found ngrok binary at: %s", candidate)
                return str(candidate)

    # Fallback: system PATH
    import shutil
    found = shutil.which("ngrok")
    if found:
        log.info("Found ngrok on PATH: %s", found)
        return found

    raise FileNotFoundError(
        "ngrok binary not found. Place ngrok.exe in the 'bin/' folder "
        "next to the application, or add it to your system PATH."
    )


# ---------------------------------------------------------------------------
# Poll the local ngrok API for the active tunnel URL
# ---------------------------------------------------------------------------
def _fetch_ngrok_url(retries: int = 15, delay: float = 1.5) -> Optional[str]:
    for _ in range(retries):
        try:
            resp = requests.get(
                "http://127.0.0.1:4040/api/tunnels", timeout=3
            )
            if resp.ok:
                data = resp.json()
                tunnels = data.get("tunnels", [])
                for t in tunnels:
                    if t.get("proto") == "https":
                        return t["public_url"]
                    if t.get("public_url"):
                        return t["public_url"]
        except Exception:
            pass
        time.sleep(delay)
    return None


# ---------------------------------------------------------------------------
# Start ngrok in a background daemon thread
# ---------------------------------------------------------------------------
def _start_ngrok(port: int, auth_token: str) -> None:
    global _tunnel_process
    try:
        ngrok = _ngrok_path()
    except FileNotFoundError as exc:
        log.warning("Tunnel disabled: %s", exc)
        return

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    # Configure auth token (writes to ngrok config)
    if auth_token:
        try:
            subprocess.run(
                [ngrok, "config", "add-authtoken", auth_token],
                capture_output=True,
                timeout=10,
                creationflags=creationflags,
            )
        except Exception as e:
            log.warning("Could not set ngrok auth token: %s", e)

    cmd = [ngrok, "http", str(port), "--log=stdout", "--log-format=json"]
    log.info("Launching ngrok: %s", " ".join(cmd))

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        with _lock:
            _tunnel_process = proc
    except Exception as exc:
        log.error("Failed to launch ngrok: %s", exc)
        return

    # Poll for URL
    url = _fetch_ngrok_url()
    if url:
        _set_public_url(url)
    else:
        log.warning("Could not retrieve ngrok public URL within timeout.")

    # Keep thread alive: drain stdout so the process does not block
    try:
        for line in proc.stdout:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if entry.get("lvl") == "eror":
                        log.warning("ngrok: %s", entry.get("msg", line))
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass


def start_tunnel(port: int = 5000, auth_token: str = "") -> None:
    """Spawn ngrok in a background daemon thread.  Non-blocking."""
    t = threading.Thread(
        target=_start_ngrok,
        args=(port, auth_token),
        daemon=True,
        name="ngrok-thread",
    )
    t.start()


def stop_tunnel() -> None:
    """Terminate the ngrok process if running."""
    global _tunnel_process
    with _lock:
        proc = _tunnel_process
    if proc and proc.poll() is None:
        proc.terminate()
        log.info("ngrok process terminated.")
