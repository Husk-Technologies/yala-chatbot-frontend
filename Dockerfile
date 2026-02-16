FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Needed for TLS connections (e.g., Upstash Redis over rediss://)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY src /app/src
COPY README.md /app/README.md
COPY backend.md /app/backend.md

EXPOSE 5000

# Production server
CMD ["sh", "-c", "gunicorn -w 2 --threads 8 -b 0.0.0.0:${PORT:-5000} src.app:app"]
