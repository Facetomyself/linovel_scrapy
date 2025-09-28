# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Configure apt sources for China
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|security.debian.org/debian-security|mirrors.ustc.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources

# System dependencies (build tools for any wheels that need compiling)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (leverage Docker layer cache)
COPY requirements.txt ./
RUN pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Copy project files
COPY . .

# Ensure entry script is executable and logs dir exists
RUN chmod +x /app/main.sh \
    && mkdir -p /app/logs

# Default command; can be overridden (e.g., list --max-pages 1)
ENTRYPOINT ["/app/main.sh"]

