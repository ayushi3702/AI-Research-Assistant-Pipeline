FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget curl gnupg libglib2.0-0 libnss3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 \
    libxfixes3 libxext6 libx11-6 libx11-xcb1 libxcb1 libpango-1.0-0 \
    libcairo2 libexpat1 libdbus-1-3 libatspi2.0-0 \
    libpangocairo-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev shared-mime-info fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY services/agents/requirements.txt ./requirements-agents.txt
COPY services/api/requirements.txt ./requirements-api.txt
RUN pip install --no-cache-dir -r requirements-agents.txt -r requirements-api.txt
RUN playwright install chromium

COPY shared/ ./shared/
COPY services/agents/ ./agents/
COPY services/api/ ./api/

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
