# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /app

# Pobranie oficjalnego binarium uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Kopiowanie definicji zależności
COPY pyproject.toml uv.lock ./

# Instalacja zależności produkcyjnych
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system
RUN uv sync --frozen --no-dev --no-install-project

# Etap docelowy (runtime)
FROM python:3.11-slim AS runtime

WORKDIR /app

# Utworzenie użytkownika nieuprzywilejowanego UID 1000
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -d /home/appuser -s /bin/bash appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Kopiowanie virtualenv z buildera
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Kopiowanie aplikacji, migracji i zasobów
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser migrations /app/migrations
COPY --chown=appuser:appuser frontend /app/frontend
COPY --chown=appuser:appuser alembic.ini pyproject.toml /app/
COPY --chown=appuser:appuser scripts/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SQLITE_DB_PATH="/app/data/movie_recommend.db"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
