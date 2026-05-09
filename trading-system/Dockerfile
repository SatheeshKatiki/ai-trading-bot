# Dockerfile for AI Intraday Trading System
# -------------------------------------------------
# Multi‑stage build:
#   1️⃣ Build stage – create a clean Python environment and install dependencies.
#   2️⃣ Runtime stage – copy only the necessary runtime files.

# ---------- Build stage ----------
FROM python:3.11-slim AS builder

# Install system dependencies needed for pandas, numpy, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create a non‑root user for security
ARG USERNAME=appuser
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ${USERNAME} && \
    useradd -m -u ${UID} -g ${GID} ${USERNAME}

# Set working directory
WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---------- Runtime stage ----------
FROM python:3.11-slim AS runtime

# Copy non‑root user from builder
COPY --from=builder /etc/passwd /etc/passwd
COPY --from=builder /etc/group /etc/group

WORKDIR /app

# Copy installed packages from builder to keep image slim
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy source code
COPY . ./

# Ensure the non‑root user owns the files
RUN chown -R appuser:appuser /app
USER appuser

# Expose common ports
#   8501 – Streamlit dashboard
EXPOSE 8501

# Default command – developers can override with e.g. "python -m trading_bot.main" or "python -m backtesting_engine.run --data-path …"
# Here we provide a convenient entrypoint that runs the Streamlit dashboard.
ENTRYPOINT ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.headless=true"]
