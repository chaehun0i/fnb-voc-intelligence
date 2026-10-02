FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY . .
RUN pip install --no-cache-dir .
ENV PYTHONPATH=/app/backend
USER app
CMD ["python", "-m", "src.ingestion.cli", "--help"]
