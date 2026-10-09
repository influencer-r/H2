"""
whatsapp.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry-point called by the payment pipeline
# ---------------------------------------------------------------------------
def send_receipt(
    phone_number: str,
    tenant_name: str,
    receipt_number: str,
    amount_paid: float,
    receipt_file: Optional[Path],
    settings: dict[str, str],
) -> str:
    """
    Attempt to send the receipt via WhatsApp.

    Returns a status string: 'SENT' | 'QUEUED' | 'FAILED' | 'DISABLED'
    """
    mode = settings.get("whatsapp_mode", "local").lower()
    log.info("WhatsApp delivery mode: %s → %s", mode, phone_number)

    if mode == "api":
        sid = settings.get("whatsapp_sid", "")
        auth_token = settings.get("whatsapp_auth_token", "")
        sender = settings.get("whatsapp_sender", "")
        if sid and auth_token and sender:
            return _send_via_api(
                phone_number=phone_number,
                tenant_name=tenant_name,
                receipt_number=receipt_number,
                amount_paid=amount_paid,
                receipt_file=receipt_file,
                sid=sid,
                auth_token=auth_token,
                sender=sender,
            )
        else:
            log.info("Twilio API credentials not configured; falling back to headless WhatsApp bridge.")
            return _send_via_local(
                phone_number=phone_number,
                tenant_name=tenant_name,
                receipt_number=receipt_number,
                amount_paid=amount_paid,
                receipt_file=receipt_file,
            )

    return _send_via_local(
        phone_number=phone_number,
        tenant_name=tenant_name,
        receipt_number=receipt_number,
        amount_paid=amount_paid,
        receipt_file=receipt_file,
    )


# ---------------------------------------------------------------------------
# Mode A: Twilio WhatsApp API
# ---------------------------------------------------------------------------
def _send_via_api(
    phone_number: str,
    tenant_name: str,
    receipt_number: str,
    amount_paid: float,
    receipt_file: Optional[Path],
    sid: str,
    auth_token: str,
    sender: str,
) -> str:
    if not all([sid, auth_token, sender]):
        log.warning(
            "WhatsApp API credentials incomplete. Set SID, Auth Token, "
            "and Sender Number in Settings."
        )
        return "FAILED"

    message_body = (
        f"✅ *Haven Stays — Payment Confirmed*\n\n"
        f"Dear *{tenant_name}*,\n"
        f"We have received your payment of *KES {amount_paid:,.2f}*.\n"
        f"Receipt No: *{receipt_number}*\n\n"
        f"Thank you for your prompt payment. 🏠"
    )

    # Normalise to E.164 (e.g. 0712345678 → +254712345678)
    to_wa = _normalise_to_whatsapp(phone_number)
    from_wa = f"whatsapp:{sender}" if not sender.startswith("whatsapp:") else sender

    try:
        from twilio.rest import Client  # type: ignore

        client = Client(sid, auth_token)

        kwargs: dict = {
            "from_": from_wa,
            "to": to_wa,
            "body": message_body,
        }

        # Attach PDF if it exists
        if receipt_file and receipt_file.exists():
            # Twilio needs a public URL; for local files we include a note
            # In a real deployment, upload to a CDN or use ngrok file serving.
            log.info(
                "PDF attachment local path: %s (upload to public URL for full delivery)",
                receipt_file,
            )

        msg = client.messages.create(**kwargs)
        log.info("WhatsApp sent via Twilio API. SID: %s", msg.sid)
        return "SENT"

    except ImportError:
        log.warning(
            "twilio package not installed. Install with: pip install twilio"
        )
        return "FAILED"
    except Exception as exc:
        log.error("WhatsApp API send failed: %s", exc)
        return "FAILED"


# ---------------------------------------------------------------------------
# Mode B: Local WhatsApp session (Headless Baileys background worker)
# ---------------------------------------------------------------------------
def _send_via_local(
    phone_number: str,
    tenant_name: str,
    receipt_number: str,
    amount_paid: float,
    receipt_file: Optional[Path],
) -> str:
    message_body = (
        f"✅ *Haven Stays — Payment Confirmed*\n\n"
        f"Dear *{tenant_name}*,\n"
        f"We have received your payment of *KES {amount_paid:,.2f}*.\n"
        f"Receipt No: *{receipt_number}*\n\n"
        f"Thank you for your prompt payment! 🏠"
    )

    # 1. Try headless background Baileys bridge first (100% silent, no browser popups)
    try:
        import requests
        payload = {
            "phone": phone_number,
            "message": message_body,
            "pdf_path": str(receipt_file) if receipt_file and receipt_file.exists() else None,
        }
        res = requests.post("http://127.0.0.1:5555/send", json=payload, timeout=8)
        if res.status_code == 200:
            log.info("WhatsApp sent silently via background bridge for %s", phone_number)
            return "SENT"
        else:
            log.warning("Background bridge returned %s: %s", res.status_code, res.text)
    except Exception as exc:
        log.warning("Background bridge not available, falling back: %s", exc)

    # 2. Fallback to pywhatkit if bridge not running
    normalised = _raw_phone(phone_number)
    try:
        import pywhatkit  # type: ignore

        pywhatkit.sendwhatmsg_instantly(
            phone_no=f"+{normalised}",
            message=message_body,
            wait_time=15,
            tab_close=False,
        )
        log.info("WhatsApp message queued via pywhatkit for %s", phone_number)
        return "SENT"
    except Exception as exc:
        log.error("Local WhatsApp send failed: %s", exc)
        return "FAILED"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _raw_phone(phone: str) -> str:
    """Strip all non-digit characters."""
    digits = "".join(c for c in phone if c.isdigit())
    # Kenya: 07xx → 2547xx
    if digits.startswith("07") and len(digits) == 10:
        digits = "254" + digits[1:]
    elif digits.startswith("7") and len(digits) == 9:
        digits = "254" + digits
    return digits


def _normalise_to_whatsapp(phone: str) -> str:
    digits = _raw_phone(phone)
    return f"whatsapp:+{digits}"
