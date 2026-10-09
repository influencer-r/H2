"""
database.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve storage path (supports CLOUD persistent volumes and local execution)
# ---------------------------------------------------------------------------
_STORAGE_ENV = os.environ.get("STORAGE_DIR")
if _STORAGE_ENV:
    STORAGE_DIR = Path(_STORAGE_ENV)
elif getattr(sys, "frozen", False):
    STORAGE_DIR = Path(sys.executable).parent / "storage"
else:
    STORAGE_DIR = Path(__file__).parent / "storage"

DB_PATH = STORAGE_DIR / "haven_stays.db"
RECEIPTS_DIR = STORAGE_DIR / "receipts"
ASSETS_DIR = STORAGE_DIR / "assets"

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_DDL = [
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name      TEXT    NOT NULL,
        phone_number   TEXT    NOT NULL UNIQUE,
        unit_number    TEXT    NOT NULL,
        monthly_rent   REAL    NOT NULL DEFAULT 0.0,
        status         TEXT    NOT NULL DEFAULT 'LOGGED_OUT'
                               CHECK(status IN ('LOGGED_IN','LOGGED_OUT')),
        move_in_date   DATETIME,
        move_out_date  DATETIME,
        created_at     DATETIME DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS payments (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id             INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
        amount_paid           REAL    NOT NULL,
        transaction_reference TEXT    NOT NULL UNIQUE,
        payment_channel       TEXT,
        payment_date          DATETIME DEFAULT (datetime('now')),
        raw_payload           TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS receipts (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        payment_id       INTEGER REFERENCES payments(id) ON DELETE CASCADE,
        tenant_id        INTEGER REFERENCES tenants(id) ON DELETE SET NULL,
        receipt_number   TEXT    NOT NULL UNIQUE,
        file_path        TEXT,
        whatsapp_status  TEXT    DEFAULT 'PENDING',
        generated_at     DATETIME DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    # Indexes for fast look-ups
    "CREATE INDEX IF NOT EXISTS idx_tenants_phone  ON tenants(phone_number)",
    "CREATE INDEX IF NOT EXISTS idx_payments_tenant ON payments(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_receipts_tenant ON receipts(tenant_id)",
]

_DEFAULT_SETTINGS = {
    "property_name":          "Haven Stays",
    "property_address":       "123 Main Street, Nairobi, Kenya",
    "property_phone":         "+254700000000",
    "mpesa_consumer_key":     "",
    "mpesa_consumer_secret":  "",
    "mpesa_passkey":          "",
    "mpesa_shortcode":        "",
    "mpesa_webhook_token":    "",
    "whatsapp_mode":          "local",          # "local" (free Baileys bridge) | "api"
    "whatsapp_sid":           "",
    "whatsapp_auth_token":    "",
    "whatsapp_sender":        "",
    "ngrok_auth_token":       "",
    "receipt_logo_path":      "",
}


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create storage dirs, run DDL, and seed default settings."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        for stmt in _DDL:
            conn.execute(stmt)

        # Seed settings only once (INSERT OR IGNORE)
        conn.executemany(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)",
            list(_DEFAULT_SETTINGS.items()),
        )
    log.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Connection context manager
# ---------------------------------------------------------------------------
@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------
def get_all_settings() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
    return row["value"] if row else default


def upsert_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def bulk_upsert_settings(data: dict[str, str]) -> None:
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            list(data.items()),
        )


# ---------------------------------------------------------------------------
# Tenant helpers
# ---------------------------------------------------------------------------
def create_tenant(
    full_name: str,
    phone_number: str,
    unit_number: str,
    monthly_rent: float,
    move_in_date: str | None = None,
) -> int:
    now = move_in_date or datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tenants(full_name,phone_number,unit_number,monthly_rent,status,move_in_date)
            VALUES (?,?,?,?,'LOGGED_IN',?)
            """,
            (full_name, phone_number, unit_number, monthly_rent, now),
        )
    return cur.lastrowid


def update_tenant(tenant_id: int, **fields) -> None:
    allowed = {"full_name", "phone_number", "unit_number", "monthly_rent", "status", "move_out_date"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [tenant_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE tenants SET {set_clause} WHERE id=?", values)


def checkout_tenant(tenant_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "UPDATE tenants SET status='LOGGED_OUT', move_out_date=? WHERE id=?",
            (now, tenant_id),
        )


def get_tenant_by_phone(phone: str) -> sqlite3.Row | None:
    # Extract only digits and match on the significant trailing 9 digits (e.g. 7XXXXXXXX)
    digits = "".join(c for c in str(phone) if c.isdigit())
    last9 = digits[-9:] if len(digits) >= 9 else digits

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM tenants WHERE status='LOGGED_IN'"
        ).fetchall()
        for r in rows:
            t_digits = "".join(c for c in str(r["phone_number"]) if c.isdigit())
            t_last9 = t_digits[-9:] if len(t_digits) >= 9 else t_digits
            if last9 and t_last9 == last9:
                return r
    return None


def get_tenant_by_unit(unit_number: str) -> sqlite3.Row | None:
    """Find the active logged-in tenant for a given unit/room number."""
    if not unit_number:
        return None
    cleaned = str(unit_number).strip().lower()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM tenants WHERE status='LOGGED_IN'").fetchall()
        for r in rows:
            if str(r["unit_number"]).strip().lower() == cleaned:
                return r
    return None


def get_all_tenants() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tenants ORDER BY created_at DESC"
        ).fetchall()


def get_tenant_by_id(tenant_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tenants WHERE id=?", (tenant_id,)
        ).fetchone()


def delete_tenant(tenant_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM receipts WHERE tenant_id=?", (tenant_id,))
        conn.execute("DELETE FROM payments WHERE tenant_id=?", (tenant_id,))
        conn.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))


def delete_payment(payment_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM receipts WHERE payment_id=?", (payment_id,))
        conn.execute("DELETE FROM payments WHERE id=?", (payment_id,))


def delete_receipt(receipt_id: int) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT file_path FROM receipts WHERE id=?", (receipt_id,)).fetchone()
        if row and row["file_path"]:
            try:
                Path(row["file_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        conn.execute("DELETE FROM receipts WHERE id=?", (receipt_id,))


# ---------------------------------------------------------------------------
# Payment helpers
# ---------------------------------------------------------------------------
def record_payment(
    tenant_id: int,
    amount_paid: float,
    transaction_reference: str,
    payment_channel: str,
    payment_date: str | None,
    raw_payload: str,
) -> int:
    pd = payment_date or datetime.utcnow().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO payments(tenant_id,amount_paid,transaction_reference,
                                 payment_channel,payment_date,raw_payload)
            VALUES (?,?,?,?,?,?)
            """,
            (tenant_id, amount_paid, transaction_reference, payment_channel, pd, raw_payload),
        )
    return cur.lastrowid


def get_payments_for_tenant(tenant_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM payments WHERE tenant_id=? ORDER BY payment_date DESC",
            (tenant_id,),
        ).fetchall()


def get_all_payments() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT p.*, t.full_name, t.unit_number, t.phone_number
            FROM payments p
            LEFT JOIN tenants t ON t.id = p.tenant_id
            ORDER BY p.payment_date DESC
            """
        ).fetchall()


# ---------------------------------------------------------------------------
# Receipt helpers
# ---------------------------------------------------------------------------
def record_receipt(
    payment_id: int,
    tenant_id: int,
    receipt_number: str,
    file_path: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO receipts(payment_id,tenant_id,receipt_number,file_path,whatsapp_status)
            VALUES (?,?,?,?,'PENDING')
            """,
            (payment_id, tenant_id, receipt_number, file_path),
        )
    return cur.lastrowid


def update_receipt_whatsapp_status(receipt_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE receipts SET whatsapp_status=? WHERE id=?", (status, receipt_id)
        )


def get_all_receipts() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT r.*, t.full_name, t.unit_number, t.phone_number
            FROM receipts r
            LEFT JOIN tenants t ON t.id = r.tenant_id
            ORDER BY r.generated_at DESC
            """
        ).fetchall()
