# Multi-stage build for Hyper Alpha Arena
FROM node:18-alpine AS frontend-builder

# Build frontend
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install -g pnpm && pnpm install
COPY frontend/ ./
RUN pnpm build

# Python backend stage
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy backend code
COPY backend/ ./backend/

# Install Python dependencies
WORKDIR /app/backend
RUN pip install --no-cache-dir -e .

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist ./static/

# Expose port
EXPOSE 8802

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8802/api/health || exit 1

# Start application with database initialization
CMD ["sh", "-c", "mkdir -p /app/data && if [ ! -f /app/data/.encryption_key ]; then python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' > /app/data/.encryption_key; fi && export HYPERLIQUID_ENCRYPTION_KEY=$(cat /app/data/.encryption_key) && python -m database.init_postgresql || true && python database/init_hyperliquid_tables.py || true && python database/init_snapshot_db.py || true && python -m uvicorn main:app --host 0.0.0.0 --port 8802"]
