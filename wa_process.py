"""
wa_process.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.

Manages the background headless Baileys WhatsApp micro-bridge.
Spawns node wa_bridge/server.js silently in a daemon thread.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_bridge_process: Optional[subprocess.Popen] = None
_lock = threading.Lock()


def _resolve_paths() -> tuple[str, str]:
    """Find node binary and server.js file path."""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent

    # Look for server.js
    candidates = [
        base / "wa_bridge" / "server.js",
        base / "_internal" / "wa_bridge" / "server.js",
        Path(__file__).parent / "wa_bridge" / "server.js",
    ]
    server_path = None
    for c in candidates:
        if c.exists():
            server_path = str(c)
            break

    node_bin = shutil.which("node")
    if not node_bin:
        # Check standard Windows node paths
        std_paths = [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
        ]
        for sp in std_paths:
            if Path(sp).exists():
                node_bin = sp
                break

    return node_bin, server_path


def start_wa_bridge() -> None:
    """Start the Baileys bridge in the background."""
    def _run():
        global _bridge_process
        node_bin, server_path = _resolve_paths()

        if not node_bin or not server_path:
            log.warning("Cannot start WhatsApp bridge: node=%s, server=%s", node_bin, server_path)
            return

        cmd = [node_bin, server_path]
        cwd = str(Path(server_path).parent)
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        log.info("Starting WhatsApp bridge: %s", " ".join(cmd))
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            with _lock:
                _bridge_process = proc

            for line in proc.stdout:
                line = line.strip()
                if line:
                    log.info("[wa_bridge] %s", line)
        except Exception as exc:
            log.error("Failed to run WhatsApp bridge: %s", exc)

    t = threading.Thread(target=_run, daemon=True, name="wa-bridge-thread")
    t.start()


def stop_wa_bridge() -> None:
    """Stop the bridge process on application exit."""
    global _bridge_process
    with _lock:
        proc = _bridge_process
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            log.info("WhatsApp bridge terminated.")
        except Exception:
            pass
