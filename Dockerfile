FROM python:3.11-slim

# Ishchi papka
WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Requirements faylini ko'chir
COPY requirements.txt .

# Python dependencies o'rnat
RUN pip install --no-cache-dir -r requirements.txt

# Loyiha kodini ko'chir
COPY . .

# Entrypoint: choose which bot script to run based on DB_TYPE
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
