# Use official Python 3.11 slim image
# (was python:3.10-slim-buster — Debian Buster went EOL in 2024 and no
# longer receives security patches; 3.11-slim matches the base image
# already used and vetted in the repo's other Dockerfile)
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Create a non-root user for security. UID/GID are build args so they
# can be matched to the host user (e.g. `--build-arg UID=$(id -u)`) when
# bind-mounting host paths like state.json/models/logs, avoiding
# permission-denied errors on those mounts.
ARG USERNAME=appuser
ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} ${USERNAME} && \
    useradd -m -u ${UID} -g ${GID} ${USERNAME}

# Create working directory
WORKDIR /app

# Install system dependencies (e.g. for pandas/xgboost if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure the non-root user owns the app directory before dropping privileges
RUN chown -R ${USERNAME}:${USERNAME} /app
USER ${USERNAME}

# Expose Streamlit port
EXPOSE 8501

# The default command will run the live bot.
# You can override this to run the dashboard via docker-compose.
CMD ["python", "-m", "trading_bot.main"]
