FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY backend/requirements/base.txt /app/backend/requirements/base.txt
COPY backend/requirements/dev.txt /app/backend/requirements/dev.txt
RUN pip install --no-cache-dir -r requirements/dev.txt
COPY backend /app/backend
EXPOSE 8000
