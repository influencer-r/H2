"""
receipts.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve base path (supports CLOUD persistent storage and local runtime)
# ---------------------------------------------------------------------------
_STORAGE_ENV = os.environ.get("STORAGE_DIR")
if _STORAGE_ENV:
    RECEIPTS_DIR = Path(_STORAGE_ENV) / "receipts"
elif getattr(sys, "frozen", False):
    RECEIPTS_DIR = Path(sys.executable).parent / "storage" / "receipts"
else:
    RECEIPTS_DIR = Path(__file__).parent / "storage" / "receipts"


# ---------------------------------------------------------------------------
# Receipt number generator (sequential, date-prefixed)
# ---------------------------------------------------------------------------
def generate_receipt_number() -> str:
    now = datetime.utcnow()
    from database import get_conn  # local import to avoid circular

    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    return f"HS-{now.strftime('%Y%m')}-{count + 1:05d}"


# ---------------------------------------------------------------------------
# ReportLab PDF builder
# ---------------------------------------------------------------------------
def build_pdf(
    receipt_number: str,
    tenant_name: str,
    unit_number: str,
    phone_number: str,
    transaction_reference: str,
    payment_channel: str,
    payment_date: str,
    amount_paid: float,
    monthly_rent: float,
    property_name: str = "Haven Stays",
    property_address: str = "",
    property_phone: str = "",
    logo_path: Optional[str] = None,
) -> Path:
    """Generate a PDF receipt and return its Path."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RECEIPTS_DIR / f"{receipt_number}.pdf"

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable, Image,
        )

        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()
        palette = {
            "dark":   colors.HexColor("#0B0F19"),
            "accent": colors.HexColor("#38BDF8"),
            "muted":  colors.HexColor("#64748B"),
            "light":  colors.HexColor("#F8FAFC"),
        }

        # Custom paragraph styles
        title_style = ParagraphStyle(
            "HSTitle",
            parent=styles["Title"],
            fontSize=22,
            textColor=palette["dark"],
            spaceAfter=2,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
        subtitle_style = ParagraphStyle(
            "HSSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=palette["muted"],
            spaceAfter=4,
            alignment=TA_CENTER,
        )
        label_style = ParagraphStyle(
            "HSLabel",
            parent=styles["Normal"],
            fontSize=9,
            textColor=palette["muted"],
            fontName="Helvetica",
        )
        value_style = ParagraphStyle(
            "HSValue",
            parent=styles["Normal"],
            fontSize=11,
            textColor=palette["dark"],
            fontName="Helvetica-Bold",
        )
        receipt_num_style = ParagraphStyle(
            "HSReceiptNum",
            parent=styles["Normal"],
            fontSize=13,
            textColor=palette["accent"],
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
        amount_style = ParagraphStyle(
            "HSAmount",
            parent=styles["Normal"],
            fontSize=26,
            textColor=palette["dark"],
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        )
        footer_style = ParagraphStyle(
            "HSFooter",
            parent=styles["Normal"],
            fontSize=8,
            textColor=palette["muted"],
            alignment=TA_CENTER,
        )

        story = []

        # ---- Logo / Header ----
        if logo_path and Path(logo_path).exists():
            try:
                story.append(Image(logo_path, width=4 * cm, height=2 * cm))
            except Exception:
                pass

        story.append(Paragraph(property_name, title_style))
        story.append(Paragraph(property_address, subtitle_style))
        story.append(Paragraph(f"Tel: {property_phone}", subtitle_style))
        story.append(Spacer(1, 0.3 * cm))
        story.append(HRFlowable(width="100%", thickness=2, color=palette["accent"]))
        story.append(Spacer(1, 0.4 * cm))

        # ---- OFFICIAL RECEIPT label ----
        story.append(Paragraph("OFFICIAL PAYMENT RECEIPT", receipt_num_style))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(f"Receipt No: {receipt_number}", receipt_num_style))
        story.append(Spacer(1, 0.5 * cm))

        # ---- Tenant info table ----
        tenant_data = [
            [Paragraph("TENANT", label_style), Paragraph("UNIT", label_style),
             Paragraph("DATE", label_style)],
            [Paragraph(tenant_name, value_style), Paragraph(unit_number, value_style),
             Paragraph(payment_date[:10] if payment_date else "", value_style)],
            [Paragraph("PHONE", label_style), Paragraph("CHANNEL", label_style),
             Paragraph("REFERENCE", label_style)],
            [Paragraph(phone_number, value_style), Paragraph(payment_channel, value_style),
             Paragraph(transaction_reference, value_style)],
        ]
        tenant_table = Table(tenant_data, colWidths=[5.5 * cm, 4 * cm, 7 * cm])
        tenant_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), palette["light"]),
            ("BACKGROUND", (0, 2), (-1, 2), palette["light"]),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(tenant_table)
        story.append(Spacer(1, 0.6 * cm))

        # ---- Itemised breakdown ----
        balance = monthly_rent - amount_paid
        items = [
            ["Description", "Amount (KES)"],
            ["Monthly Rent", f"{monthly_rent:,.2f}"],
            ["Amount Paid", f"{amount_paid:,.2f}"],
            ["Outstanding Balance", f"{max(balance, 0.0):,.2f}"],
        ]
        item_table = Table(items, colWidths=[11 * cm, 5.5 * cm])
        item_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), palette["dark"]),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 10),
            ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, palette["light"]]),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            # Highlight amount paid row
            ("BACKGROUND",    (0, 2), (-1, 2), colors.HexColor("#E0F2FE")),
            ("TEXTCOLOR",     (0, 2), (-1, 2), palette["dark"]),
            ("FONTNAME",      (0, 2), (-1, 2), "Helvetica-Bold"),
        ]))
        story.append(item_table)
        story.append(Spacer(1, 0.5 * cm))

        # ---- Big amount ----
        story.append(HRFlowable(width="100%", thickness=1, color=palette["accent"]))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"KES {amount_paid:,.2f}", amount_style))
        story.append(Paragraph("AMOUNT RECEIVED", subtitle_style))
        story.append(Spacer(1, 0.5 * cm))

        # ---- Footer ----
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0")))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            f"This is a computer-generated receipt and requires no signature. "
            f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC by {property_name}.",
            footer_style,
        ))
        story.append(Spacer(1, 0.15 * cm))
        dev_credit_style = ParagraphStyle(
            "HSDevCredit",
            parent=styles["Normal"],
            fontSize=7.5,
            textColor=colors.HexColor("#0284C7"),
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        )
        story.append(Paragraph(
            "Powered by Haven Stays &bull; Developed by READON ADOLA DEVs (+254 798 792 730)",
            dev_credit_style,
        ))

        doc.build(story)
        log.info("PDF receipt generated: %s", out_path)

    except ImportError:
        # ReportLab not installed — write a plain-text stub
        log.warning("ReportLab not available; writing plain-text receipt stub.")
        out_path = RECEIPTS_DIR / f"{receipt_number}.txt"
        with open(out_path, "w") as f:
            f.write(f"""
HAVEN STAYS — OFFICIAL RECEIPT
{'='*40}
Receipt No   : {receipt_number}
Tenant       : {tenant_name}
Unit         : {unit_number}
Phone        : {phone_number}
Date         : {payment_date}
Channel      : {payment_channel}
Reference    : {transaction_reference}
{'='*40}
Monthly Rent : KES {monthly_rent:,.2f}
Amount Paid  : KES {amount_paid:,.2f}
Balance      : KES {max(monthly_rent - amount_paid, 0.0):,.2f}
{'='*40}
{property_name} | {property_address} | {property_phone}
Powered by Haven Stays • Developed by READON ADOLA DEVs (+254 798 792 730)
""")

    return out_path
