"""
app.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, jsonify, request, render_template,
    send_from_directory, abort,
)

# ---------------------------------------------------------------------------
# Bootstrap: ensure the storage dirs exist and DB is ready
# ---------------------------------------------------------------------------
import database as db

db.init_db()

# ---------------------------------------------------------------------------
# Optional tunnel (started lazily in main.py / __main__)
# ---------------------------------------------------------------------------
import tunnel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app setup
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _BASE = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    _BASE = Path(__file__).parent

_STORAGE_ENV = os.environ.get("STORAGE_DIR")
if _STORAGE_ENV:
    _STORAGE_ROOT = Path(_STORAGE_ENV)
elif getattr(sys, "frozen", False):
    _STORAGE_ROOT = Path(sys.executable).parent / "storage"
else:
    _STORAGE_ROOT = _BASE / "storage"

app = Flask(
    __name__,
    template_folder=str(_BASE / "templates"),
    static_folder=str(_BASE / "static"),
)
app.secret_key = os.urandom(32)


# ============================================================
# STATIC FILES — serve placeholder images and local assets
# ============================================================
@app.route("/storage/assets/<path:filename>")
def serve_asset(filename):
    assets_dir = _STORAGE_ROOT / "assets"
    return send_from_directory(str(assets_dir), filename)


@app.route("/storage/receipts/<path:filename>")
def serve_receipt(filename):
    receipts_dir = _STORAGE_ROOT / "receipts"
    return send_from_directory(str(receipts_dir), filename)


# ============================================================
# MAIN SPA ROUTE
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# API — DASHBOARD STATS
# ============================================================
@app.route("/api/v1/dashboard")
def api_dashboard():
    tenants  = db.get_all_tenants()
    payments = db.get_all_payments()
    receipts = db.get_all_receipts()

    active_statuses = {"PAID", "DUE_SOON", "DUE_TODAY", "OVERDUE", "DEFAULTING"}
    overdue_statuses = {"OVERDUE", "DEFAULTING"}

    active         = sum(1 for t in tenants if t.get("payment_status") in active_statuses)
    overdue_list   = [t for t in tenants if t.get("payment_status") in overdue_statuses]
    overdue_count  = len(overdue_list)
    overdue_amount = sum(t.get("balance_due", 0) for t in overdue_list)
    total_collected = sum(p["amount_paid"] for p in payments)

    return jsonify({
        "total_tenants":    len(tenants),
        "active_tenants":   active,
        "total_payments":   len(payments),
        "total_collected":  total_collected,
        "total_receipts":   len(receipts),
        "overdue_count":    overdue_count,
        "overdue_amount":   overdue_amount,
    })


# ============================================================
# API — TENANTS
# ============================================================
@app.route("/api/v1/tenants", methods=["GET"])
def api_list_tenants():
    rows = db.get_all_tenants()   # already list[dict] with overdue info
    return jsonify(rows)


@app.route("/api/v1/tenants", methods=["POST"])
def api_create_tenant():
    data = request.get_json(force=True)
    required = ("full_name", "phone_number", "unit_number", "monthly_rent")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        tid = db.create_tenant(
            full_name=data["full_name"].strip(),
            phone_number=data["phone_number"].strip(),
            unit_number=data["unit_number"].strip(),
            monthly_rent=float(data["monthly_rent"]),
            move_in_date=data.get("move_in_date"),
            due_day=int(data.get("due_day", 5)),
        )
        return jsonify({"id": tid, "message": "Tenant checked in successfully."}), 201
    except Exception as exc:
        log.error("Create tenant error: %s", exc)
        return jsonify({"error": str(exc)}), 409


@app.route("/api/v1/tenants/<int:tenant_id>", methods=["GET"])
def api_get_tenant(tenant_id):
    row = db.get_tenant_by_id(tenant_id)
    if not row:
        abort(404)
    return jsonify(dict(row))


@app.route("/api/v1/tenants/<int:tenant_id>", methods=["PUT"])
def api_update_tenant(tenant_id):
    data = request.get_json(force=True)
    allowed = {"full_name", "phone_number", "unit_number", "monthly_rent", "status", "due_day"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields to update."}), 400
    try:
        db.update_tenant(tenant_id, **updates)
        return jsonify({"message": "Tenant updated."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/v1/tenants/<int:tenant_id>/checkout", methods=["POST"])
def api_checkout_tenant(tenant_id):
    row = db.get_tenant_by_id(tenant_id)
    if not row:
        abort(404)
    db.checkout_tenant(tenant_id)
    return jsonify({"message": f"Tenant '{row['full_name']}' checked out."})


@app.route("/api/v1/tenants/<int:tenant_id>", methods=["DELETE"])
def api_delete_tenant(tenant_id):
    db.delete_tenant(tenant_id)
    return jsonify({"message": "Tenant deleted."})


# ============================================================
# API — PAYMENTS
# ============================================================
@app.route("/api/v1/payments", methods=["GET"])
def api_list_payments():
    rows = db.get_all_payments()
    return jsonify([dict(r) for r in rows])


@app.route("/api/v1/payments/manual", methods=["POST"])
def api_manual_payment():
    """Allow manual entry of a payment from the admin UI."""
    data = request.get_json(force=True)
    required = ("tenant_id", "amount_paid", "transaction_reference", "payment_channel")
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing: {', '.join(missing)}"}), 400

    tenant = db.get_tenant_by_id(int(data["tenant_id"]))
    if not tenant:
        return jsonify({"error": "Tenant not found."}), 404

    return _process_payment(
        tenant=tenant,
        amount_paid=float(data["amount_paid"]),
        transaction_reference=data["transaction_reference"],
        payment_channel=data["payment_channel"],
        payment_date=data.get("payment_date"),
        raw_payload=json.dumps(data),
    )


@app.route("/api/payments/callback", methods=["GET", "POST"])
@app.route("/api/v1/payments/webhook", methods=["GET", "POST"])
def api_payment_webhook():
    """
    Universal payment webhook / callback endpoint.
    Supports M-Pesa Daraja C2B/STK-push callbacks, Paystack, Flutterwave.
    """
    if request.method == "GET":
        return jsonify({
            "status": "active",
            "service": "Haven Stays M-Pesa Payment Callback",
            "timestamp": datetime.utcnow().isoformat(),
        }), 200

    raw_body = request.get_data(as_text=True)
    payload = {}

    try:
        payload = request.get_json(force=True) or {}
    except Exception:
        pass

    log.info("Webhook received: %.500s", raw_body)

    # ---- M-Pesa Daraja C2B / STK Push ----
    phone, amount, ref, channel = None, None, None, "M-Pesa"
    bill_ref = (
        payload.get("BillRefNumber")
        or payload.get("billRefNumber")
        or payload.get("AccountReference")
        or ""
    )

    # STK push result
    stk = payload.get("Body", {}).get("stkCallback", {})
    if stk:
        meta = {
            item["Name"]: item.get("Value")
            for item in stk.get("CallbackMetadata", {}).get("Item", [])
        }
        phone = str(meta.get("PhoneNumber", ""))
        amount = float(meta.get("Amount", 0))
        ref = meta.get("MpesaReceiptNumber") or meta.get("CheckoutRequestID")

    # Daraja C2B (paybill / till)
    elif "TransactionType" in payload:
        phone = payload.get("MSISDN") or payload.get("PhoneNumber", "")
        amount = float(payload.get("TransAmount") or payload.get("Amount", 0))
        ref = payload.get("TransID") or payload.get("TransactionReference", "")
        channel = payload.get("TransactionType", "M-Pesa")

    # Paystack
    elif payload.get("event", "").startswith("charge"):
        data = payload.get("data", {})
        customer = data.get("customer", {})
        phone = customer.get("phone", "")
        amount = float(data.get("amount", 0)) / 100  # Paystack sends kobo
        ref = data.get("reference", "")
        channel = "Paystack"

    # Flutterwave
    elif "flw_ref" in payload or payload.get("event", "").startswith("charge"):
        data = payload.get("data", {})
        phone = data.get("customer", {}).get("phone_number", "")
        amount = float(data.get("amount", 0))
        ref = data.get("tx_ref") or data.get("flw_ref", "")
        channel = "Flutterwave"

    # Generic fallback
    if not phone:
        phone = (payload.get("phone") or payload.get("msisdn") or
                 payload.get("PhoneNumber") or "")
    if not amount:
        amount = float(payload.get("amount") or payload.get("Amount") or 0)
    if not ref:
        ref = (payload.get("reference") or payload.get("TransID") or
               payload.get("transactionId") or f"WH-{datetime.utcnow().timestamp():.0f}")

    if not phone or amount <= 0:
        return jsonify({"ResultCode": 0, "ResultDesc": "Ignored: insufficient payload data."}), 200

    # 1. Look up tenant by phone number
    tenant = db.get_tenant_by_phone(phone)

    # 2. If phone not matched, attempt lookup by Unit / BillRefNumber
    if not tenant and bill_ref:
        tenant = db.get_tenant_by_unit(bill_ref)

    if not tenant:
        log.info("No active tenant matched phone %s or billRef %s", phone, bill_ref)
        return jsonify({"ResultCode": 0, "ResultDesc": "No matching active tenant."}), 200

    result = _process_payment(
        tenant=tenant,
        amount_paid=amount,
        transaction_reference=ref,
        payment_channel=channel,
        payment_date=None,
        raw_payload=raw_body,
    )
    return result


def _process_payment(tenant, amount_paid, transaction_reference,
                     payment_channel, payment_date, raw_payload):
    """Shared payment processing logic: record → receipt → WhatsApp."""
    try:
        payment_id = db.record_payment(
            tenant_id=tenant["id"],
            amount_paid=amount_paid,
            transaction_reference=transaction_reference,
            payment_channel=payment_channel,
            payment_date=payment_date,
            raw_payload=raw_payload,
        )
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            return jsonify({"error": "Duplicate transaction reference."}), 409
        return jsonify({"error": str(exc)}), 500

    # Generate receipt in a background thread so the webhook returns fast
    threading.Thread(
        target=_async_receipt_and_notify,
        args=(payment_id, tenant, amount_paid, transaction_reference,
              payment_channel, payment_date),
        daemon=True,
    ).start()

    return jsonify({
        "ResultCode": 0,
        "ResultDesc": "Payment recorded.",
        "payment_id": payment_id,
    }), 201


def _async_receipt_and_notify(payment_id, tenant, amount_paid,
                               transaction_reference, payment_channel, payment_date):
    """Run receipt generation + WhatsApp dispatch in background thread."""
    from receipts import generate_receipt_number, build_pdf
    from whatsapp import send_receipt

    settings = db.get_all_settings()

    try:
        receipt_number = generate_receipt_number()
        pdf_path = build_pdf(
            receipt_number=receipt_number,
            tenant_name=tenant["full_name"],
            unit_number=tenant["unit_number"],
            phone_number=tenant["phone_number"],
            transaction_reference=transaction_reference,
            payment_channel=payment_channel,
            payment_date=payment_date or datetime.utcnow().isoformat(),
            amount_paid=amount_paid,
            monthly_rent=tenant["monthly_rent"],
            property_name=settings.get("property_name", "Haven Stays"),
            property_address=settings.get("property_address", ""),
            property_phone=settings.get("property_phone", ""),
            logo_path=settings.get("receipt_logo_path") or None,
        )

        receipt_id = db.record_receipt(
            payment_id=payment_id,
            tenant_id=tenant["id"],
            receipt_number=receipt_number,
            file_path=str(pdf_path),
        )

        wa_status = send_receipt(
            phone_number=tenant["phone_number"],
            tenant_name=tenant["full_name"],
            receipt_number=receipt_number,
            amount_paid=amount_paid,
            receipt_file=pdf_path,
            settings=settings,
        )

        db.update_receipt_whatsapp_status(receipt_id, wa_status)
        log.info(
            "Payment pipeline complete. receipt=%s whatsapp=%s",
            receipt_number, wa_status,
        )
    except Exception as exc:
        log.error("Async receipt/notify error: %s", exc, exc_info=True)


@app.route("/api/v1/payments/<int:payment_id>", methods=["DELETE"])
def api_delete_payment(payment_id):
    db.delete_payment(payment_id)
    return jsonify({"message": "Payment record deleted."})


# ============================================================
# API — RECEIPTS
# ============================================================
@app.route("/api/v1/receipts", methods=["GET"])
def api_list_receipts():
    rows = db.get_all_receipts()
    return jsonify([dict(r) for r in rows])


@app.route("/api/v1/receipts/<int:receipt_id>", methods=["DELETE"])
def api_delete_receipt(receipt_id):
    db.delete_receipt(receipt_id)
    return jsonify({"message": "Receipt deleted."})


# ============================================================
# API — WHATSAPP PAIRING & TESTING
# ============================================================
@app.route("/api/v1/whatsapp/status", methods=["GET"])
def api_whatsapp_status():
    """Poll status of background headless WhatsApp bridge."""
    try:
        import requests
        r = requests.get("http://127.0.0.1:5555/status", timeout=2)
        if r.status_code == 200:
            return jsonify(r.json())
    except Exception:
        pass
    return jsonify({"connected": False, "qr": None, "user": None})


@app.route("/api/v1/whatsapp/pair", methods=["POST"])
def api_whatsapp_pair():
    """Launch WhatsApp Web in browser for local pairing."""
    import webbrowser
    webbrowser.open("https://web.whatsapp.com")
    return jsonify({"message": "WhatsApp Web opened in your browser. Scan the QR code to pair your device."})


@app.route("/api/v1/whatsapp/test", methods=["POST"])
def api_whatsapp_test():
    """Send test WhatsApp message to verify connection."""
    data = request.get_json(force=True) or {}
    phone = data.get("phone", "").strip()
    if not phone:
        return jsonify({"error": "Phone number is required."}), 400

    from whatsapp import send_receipt
    settings = db.get_all_settings()
    status = send_receipt(
        phone_number=phone,
        tenant_name="Landlord Test",
        receipt_number="TEST-001",
        amount_paid=100.0,
        receipt_file=None,
        settings=settings,
    )
    return jsonify({"status": status, "message": f"Test message dispatched. Status: {status}"})


# ============================================================
# API — SETTINGS
# ============================================================
@app.route("/api/v1/settings", methods=["GET"])
def api_get_settings():
    settings = db.get_all_settings()
    # Redact secrets from GET response (show only first 4 chars)
    sensitive = {"whatsapp_auth_token", "mpesa_consumer_secret", "mpesa_passkey"}
    safe = {}
    for k, v in settings.items():
        if k in sensitive and len(v) > 4:
            safe[k] = v[:4] + "●●●●●●●●"
        else:
            safe[k] = v
    return jsonify(safe)


@app.route("/api/v1/settings", methods=["POST"])
def api_save_settings():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Payload must be a JSON object."}), 400

    # Strip redacted values before saving
    clean = {k: v for k, v in data.items() if "●" not in str(v)}
    db.bulk_upsert_settings(clean)
    return jsonify({"message": "Settings saved."})


# ============================================================
# API — TUNNEL STATUS (stubbed — ngrok removed from UI)
# ============================================================
@app.route("/api/v1/tunnel/status", methods=["GET"])
def api_tunnel_status():
    return jsonify({"active": False, "url": "", "webhook_url": ""})


# ============================================================
# HEALTH CHECK
# ============================================================
@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": datetime.utcnow().isoformat()})


# ============================================================
# Entry point when running directly (cloud or headless)
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0")

    # Only start ngrok if explicitly enabled or on local machine
    if os.environ.get("ENABLE_NGROK") == "1":
        auth_token = db.get_setting("ngrok_auth_token")
        tunnel.start_tunnel(port=port, auth_token=auth_token)

    try:
        from waitress import serve
        log.info("Starting Haven Stays via Waitress on %s:%d ...", host, port)
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        log.info("Starting Haven Stays via Flask dev server on %s:%d ...", host, port)
        app.run(host=host, port=port, debug=False, threaded=True)
