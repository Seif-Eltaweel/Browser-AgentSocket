# AgentSocket-Browser Dockerfile
# Headless Chromium + FastAPI Gateway + FastMCP Server

FROM python:3.11-slim

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV AGENTSOCKET_PORT=8000
ENV DISPLAY=:99

# Install system dependencies, Chromium, and Xvfb for headless virtual display
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    xvfb \
    xauth \
    procps \
    curl \
    git \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY server/ ./server/
COPY extension/ ./extension/
COPY tests/ ./tests/
COPY README.md .

# Create logs directory
RUN mkdir -p /app/server/logs

# Startup entrypoint script
RUN echo '#!/bin/bash\n\
echo "Starting Xvfb virtual display on :99..."\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
sleep 2\n\
echo "Starting AgentSocket-Browser FastAPI Gateway on port ${AGENTSOCKET_PORT}..."\n\
python -m uvicorn server.socket_server:app --host 0.0.0.0 --port ${AGENTSOCKET_PORT}\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Expose HTTP / WebSocket gateway port
EXPOSE 8000

# Run entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
