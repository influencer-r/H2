# Haven Stays — Cloud Property Management & Automated Billing

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/influencer-r/H2)
[![Engineered By](https://img.shields.io/badge/Engineered%20By-READON%20ADOLA%20DEVs-0284c7.svg)](https://wa.me/254798792730)

> **24/7 Autonomous Cloud Web Application & Offline-Ready Property Management Suite.**  
> Real-time M-Pesa automated payment detection, instant PDF receipt generation, and headless WhatsApp dispatch with zero Twilio fees.

---

## 👨‍💻 Engineering & Developer Sign-Off

- **Lead Engineer:** READON ADOLA
- **Company / Agency:** READON ADOLA DEVs
- **Direct Support / WhatsApp:** [+254 798 792 730](https://wa.me/254798792730)
- **Repository:** [https://github.com/influencer-r/H2.git](https://github.com/influencer-r/H2.git)

---

## ✨ Features

| Feature | Details |
|---|---|
| **24/7 Cloud Automation** | Hosted permanently on Render. Tenants receive receipts even when landlord's devices are turned off. |
| **Instant M-Pesa Detection** | Webhooks at `/api/payments/callback` match tenants by phone or unit number and log payments in seconds. |
| **Automated Branded PDF Receipts** | Generated via ReportLab with official breakdown, watermarked with developer sign-off. |
| **Zero-Fee WhatsApp Bot** | Embedded headless Baileys WhatsApp Web bridge. Scan QR code once from your phone browser. |
| **Responsive Dark UI** | Sleek glassmorphism web dashboard with real-time analytics, check-ins, and payment charts. |
| **Persistent Data Storage** | SQLite and WhatsApp authentication sessions retained permanently on cloud disk. |
| **Keep-Alive Endpoint** | `/health` endpoint for free 5-minute pings via UptimeRobot to ensure 100% uptime. |

---

## 🚀 1-Click Deployment on Render

This repository includes a multi-service `Dockerfile` and `render.yaml` configured to run both Python (Flask / Waitress) and Node.js (`wa_bridge`) in a single supervised container.

### Step 1: Connect Repository
1. Log into [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint** or **Web Service**.
3. Select this repository: `https://github.com/influencer-r/H2`.

### Step 2: Configure Environment
- **Runtime:** `Docker`
- **Instance Type:** `Free`
- **Health Check Path:** `/health`
- **Persistent Disk (Optional):** Mount path `/var/data` (set `STORAGE_DIR=/var/data`).

---

## 📱 WhatsApp Linking Instructions (For Landlords)

1. Open your live Haven Stays URL (e.g. `https://haven.onrender.com`).
2. Go to **Settings** → **WhatsApp Integration**.
3. Point your phone's WhatsApp (**Linked Devices** → **Link a Device**) at the displayed QR code.
4. Done! All tenant payments will trigger automated PDF receipts directly to their WhatsApp.

---

## 📞 Developer Support
For custom integrations, feature requests, or technical assistance:
- **WhatsApp / Call:** [+254 798 792 730](https://wa.me/254798792730)
- **Engineered with precision by READON ADOLA DEVs.**
