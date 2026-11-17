
FROM python:3.12-slim

RUN python -m pip install --upgrade pip

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gcc \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 estateai \
    && useradd --system --uid 10001 --gid estateai \
       --home-dir /app estateai

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=estateai:estateai app ./app
COPY --chown=estateai:estateai migrations ./migrations
COPY --chown=estateai:estateai scripts ./scripts
COPY --chown=estateai:estateai alembic.ini ./alembic.ini

USER 10001:10001

EXPOSE 8000

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=60s \
    --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
