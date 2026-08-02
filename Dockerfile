# syntax=docker/dockerfile:1

FROM python:3.14-slim AS builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt


FROM python:3.14-slim AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
ENV PATH="/opt/venv/bin:$PATH"
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser --chmod=755 docker/entrypoint.sh ./docker/
USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]