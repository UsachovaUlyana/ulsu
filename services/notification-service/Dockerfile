FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY services/notification-service/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY services/_shared /app/shared
COPY services/notification-service /app/

ENV PYTHONPATH=/app

EXPOSE 8004

CMD ["python", "-m", "app.main"]
