"""
server.py — Haven Stays Cloud Server Entrypoint
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("haven_cloud")

# Initialize database
import database as db
db.init_db()

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")

    log.info("==================================================")
    log.info(" Haven Stays Cloud Server")
    log.info(" Engineered by READON ADOLA DEVs (+254 798 792 730)")
    log.info(" Listening on http://%s:%d", host, port)
    log.info("==================================================")

    from waitress import serve
    serve(app, host=host, port=port, threads=8)
