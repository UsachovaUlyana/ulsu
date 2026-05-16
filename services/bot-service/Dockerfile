FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY services/bot-service/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY services/_shared /app/shared
COPY services/bot-service /app/
COPY services/bot-service/models/model.bin /app/models/model.bin

ENV PYTHONPATH=/app

CMD ["python", "-m", "app.main"]
