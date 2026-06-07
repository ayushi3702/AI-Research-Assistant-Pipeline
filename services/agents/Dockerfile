FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget curl gnupg libglib2.0-0 libnss3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libxfixes3 libxext6 libx11-6 libx11-xcb1 libxcb1 libpango-1.0-0 \
    libcairo2 libexpat1 libdbus-1-3 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY services/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY shared/ ./shared/
COPY services/agents/ ./agents/

ENV PYTHONPATH=/app

CMD ["python", "agents/orchestrator.py"]
