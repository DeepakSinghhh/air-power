# Offline bundle: everything (datasets, trained models, benchmark cache, built UI) is baked into the
# image at build time, so the container runs with no network access — e.g. on an air-gapped edge server.

FROM node:22-slim AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/tatpar backend/tatpar
RUN pip install --no-cache-dir -e backend
COPY data/env data/env
COPY docs docs
# Build data, models and the benchmark cache inside the image (needs internet only at build time).
ARG QUICK=0
RUN cd backend && python -m tatpar.pipelines.build_all && \
    if [ "$QUICK" = "1" ]; then python -m tatpar.pipelines.bench --quick; else python -m tatpar.pipelines.bench; fi
COPY --from=ui /app/frontend/dist frontend/dist
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "tatpar.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
