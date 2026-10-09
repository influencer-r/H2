/**
 * server.js — Haven Stays WhatsApp Bridge
 * Headless Baileys WhatsApp automation microservice
 * Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
 * Copyright (c) 2026 READON ADOLA. All rights reserved.
 */

const http = require('http');
const path = require('path');
const fs = require('fs');
const qrcode = require('qrcode');
const pino = require('pino');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys');

const PORT = parseInt(process.env.WA_BRIDGE_PORT, 10) || 5555;
const sessionDir = process.env.WA_SESSION_DIR 
  || (process.env.STORAGE_DIR ? path.join(process.env.STORAGE_DIR, 'wa_session') : path.resolve(__dirname, '..', 'storage', 'wa_session'));

if (!fs.existsSync(sessionDir)) {
  fs.mkdirSync(sessionDir, { recursive: true });
}

let sock = null;
let currentQR = null;
let isConnected = false;
let userJid = null;

async function startWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
  const logger = pino({ level: 'silent' });

  sock = makeWASocket({
    auth: state,
    logger,
    printQRInTerminal: false,
    syncFullHistory: false
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      try {
        currentQR = await qrcode.toDataURL(qr, { margin: 2, scale: 6 });
      } catch (err) {
        currentQR = null;
      }
      isConnected = false;
    }

    if (connection === 'open') {
      isConnected = true;
      currentQR = null;
      userJid = sock.user ? sock.user.id : null;
      console.log('[wa_bridge] WhatsApp connected successfully.');
    } else if (connection === 'close') {
      isConnected = false;
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
      console.log('[wa_bridge] Connection closed. Reconnecting:', shouldReconnect);
      if (shouldReconnect) {
        setTimeout(startWhatsApp, 3000);
      } else {
        // Logged out
        try {
          fs.rmSync(sessionDir, { recursive: true, force: true });
        } catch (_) {}
        setTimeout(startWhatsApp, 2000);
      }
    }
  });
}

startWhatsApp().catch(err => console.error('[wa_bridge] Startup error:', err));

// HTTP API Server
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'GET' && url.pathname === '/status') {
    return res.end(JSON.stringify({
      connected: isConnected,
      qr: currentQR,
      user: userJid
    }));
  }

  if (req.method === 'POST' && url.pathname === '/send') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', async () => {
      try {
        const data = JSON.parse(body || '{}');
        const phone = data.phone;
        const text = data.message;
        const pdfPath = data.pdf_path;

        if (!phone || !text) {
          res.statusCode = 400;
          return res.end(JSON.stringify({ error: 'Missing phone or message' }));
        }

        if (!isConnected || !sock) {
          res.statusCode = 503;
          return res.end(JSON.stringify({ error: 'WhatsApp is not connected. Scan QR code first.' }));
        }

        // Clean phone number (Kenya: 07xx -> 2547xx)
        let digits = String(phone).replace(/\D/g, '');
        if (digits.startsWith('0') && digits.length === 10) {
          digits = '254' + digits.substring(1);
        } else if (digits.startsWith('7') && digits.length === 9) {
          digits = '254' + digits;
        }

        const jid = `${digits}@s.whatsapp.net`;

        // Send text receipt
        await sock.sendMessage(jid, { text });

        // Optionally send PDF if file exists
        if (pdfPath && fs.existsSync(pdfPath)) {
          const buffer = fs.readFileSync(pdfPath);
          const fileName = path.basename(pdfPath);
          await sock.sendMessage(jid, {
            document: buffer,
            mimetype: 'application/pdf',
            fileName: fileName
          });
        }

        res.end(JSON.stringify({ status: 'SENT', jid }));
      } catch (err) {
        console.error('[wa_bridge] Send error:', err);
        res.statusCode = 500;
        res.end(JSON.stringify({ error: String(err) }));
      }
    });
    return;
  }

  if (req.method === 'POST' && url.pathname === '/restart') {
    try {
      if (sock) {
        try { sock.end(); } catch (_) {}
      }
      setTimeout(startWhatsApp, 1000);
      return res.end(JSON.stringify({ message: 'Bridge restarted' }));
    } catch (err) {
      res.statusCode = 500;
      return res.end(JSON.stringify({ error: String(err) }));
    }
  }

  res.statusCode = 404;
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[wa_bridge] Listening on http://127.0.0.1:${PORT}`);
});
