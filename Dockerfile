FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/studio/frontend

COPY studio/frontend/package.json studio/frontend/package-lock.json ./
RUN npm ci

COPY studio/frontend ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/studio/backend \
    UNSLOTH_IS_PRESENT=1 \
    UNSLOTH_NO_TORCH=1 \
    UNSLOTH_STUDIO_HOME=/data \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    COGNIX_RAILWAY=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

COPY studio/backend /app/studio/backend
COPY --from=frontend-build /build/studio/frontend/dist /app/studio/frontend/dist

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r /app/studio/backend/requirements/studio.txt \
    && python -m pip install pydantic \
    && python -m pip install --no-deps -r /app/studio/backend/requirements/no-torch-runtime.txt \
    && python -m pip install --no-deps \
        "transformers==4.57.6" \
        "peft==0.18.1" \
        "sentence-transformers==5.2.0" \
        "trl==0.23.1"

RUN mkdir -p /data

EXPOSE 8080

CMD ["sh", "-c", "python /app/studio/backend/run.py --host 0.0.0.0 --port ${PORT:-8080} --frontend /app/studio/frontend/dist --no-cloudflare"]
