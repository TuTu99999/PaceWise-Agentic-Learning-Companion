# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements-runtime.lock ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --user --require-hashes -r requirements-runtime.lock

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# OCR is a bounded fallback for image-only course PDFs. It is not used when
# the PDF already has a text layer.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-vie \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip setuptools wheel

# Security: run as non-root user
RUN useradd -m appuser

# Copy dependencies into a location the non-root user can traverse.
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy only the backend runtime code. Other services use their own Dockerfile.
COPY src ./src
# The same immutable image runs the one-shot schema task before ECS replaces
# API/worker tasks. No development or simulator scripts are copied.
COPY scripts/migrate_database.py ./scripts/migrate_database.py
COPY scripts/migrate_course_materials_to_s3.py ./scripts/migrate_course_materials_to_s3.py
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/readyz')" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
