FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build essentials, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and config
COPY . .

# Create persistent directories
RUN mkdir -p /app/data /app/logs

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default command runs the bot in paper mode (or uses .env settings)
CMD ["python", "run_live_bot.py", "--live"]

