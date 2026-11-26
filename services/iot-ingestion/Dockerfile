FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY libs/common /tmp/warehouse-common
RUN pip install --no-cache-dir /tmp/warehouse-common

COPY services/iot-ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/iot-ingestion/*.py .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
