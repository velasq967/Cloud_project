FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Paquete compartido del monorepo.
COPY libs/common /tmp/warehouse-common
RUN pip install --no-cache-dir /tmp/warehouse-common

COPY services/warehouse-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/warehouse-api/main.py .
COPY services/warehouse-api/app ./app
COPY services/warehouse-api/tests ./tests
COPY services/warehouse-api/alembic.ini .
COPY services/warehouse-api/migrations ./migrations
COPY services/warehouse-api/scripts ./scripts

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "scripts/entrypoint.sh"]
