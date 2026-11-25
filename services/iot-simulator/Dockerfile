FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY services/iot-simulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/iot-simulator/*.py .

RUN mkdir -p /data \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /data
USER appuser

CMD ["python", "main.py"]
