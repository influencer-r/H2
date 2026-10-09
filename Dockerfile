# ============================================================
# Haven Stays — Multi-Service Cloud Docker Container
# Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
# ============================================================

FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    STORAGE_DIR=/app/storage \
    PORT=5000

# Install Node.js 20, supervisor, curl, and certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    supervisor \
    ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Node.js dependencies for wa_bridge
WORKDIR /app/wa_bridge
COPY wa_bridge/package*.json ./
RUN npm install --omit=dev --no-audit --no-fund

WORKDIR /app

# Copy application code
COPY . .

# Ensure storage directories exist
RUN mkdir -p /app/storage/assets /app/storage/receipts /app/storage/wa_session /var/log/supervisor /etc/supervisor/conf.d

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Render web service port
EXPOSE 5000 10000

# Start supervisor managing Flask and WhatsApp bridge
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
