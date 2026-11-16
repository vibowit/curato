# Wdrożenie Docker + SQLite (WAL) na Proxmox VE (LXC) & MCP SSE

Wzorcowa architektura wdrożeniowa i procedury operacyjne dla uruchamiania aplikacji opartej na FastAPI, SQLite i serwerze MCP w kontenerze Docker na hoście Proxmox VE (kontener Debian LXC z Dockerem) jako usługa 24/7.

---

## 1. Architektura uprawnień wolumenu SQLite (WAL)

### Problem
SQLite w trybie WAL (`PRAGMA journal_mode=WAL;`) wymaga tworzenia i modyfikowania plików tymczasowych (`movie_recommend.db-wal` oraz `movie_recommend.db-shm`) **w tym samym katalogu**, w którym znajduje się plik bazy danych. Jeśli proces wewnątrz kontenera działa jako użytkownik nieuprzywilejowany (np. `appuser` o UID `1000`), a montowany wolumen z hosta należy do `root:root`, SQLite zgłasza błąd:
`sqlite3.OperationalError: unable to open database file`.

### Rozwiązanie
1. Kontener tworzy dedykowanego użytkownika i grupę o stałym UID/GID:
   ```dockerfile
   RUN groupadd -g 1000 appuser && \
       useradd -u 1000 -g appuser -m -s /bin/bash appuser
   ```
2. Na hoście (LXC) katalog bazy danych (`data/`) musi mieć nadane uprawnienia dla UID 1000:
   ```bash
   sudo chown -R 1000:1000 ./data
   sudo chmod 775 ./data
   ```
3. W skrypcie `entrypoint.sh` przed startem `uvicorn` weryfikowane są uprawnienia do zapisu w katalogu bazy danych.

---

## 2. Wieloetapowy `Dockerfile` z `uv`

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /build

# Instalacja uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Kopiowanie definicji zależności
COPY pyproject.toml uv.lock ./

# Instalacja zależności w dedykowanym virtualenv
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

# Etap docelowy (runtime)
FROM python:3.11-slim AS runtime

WORKDIR /app

# Utworzenie użytkownika nieuprzywilejowanego
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -d /home/appuser -s /bin/bash appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Skopiowanie środowiska wirtualnego z etapu builder
COPY --from=builder --chown=appuser:appuser /build/.venv /app/.venv

# Skopiowanie kodu aplikacji, migracji i frontendu
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser migrations /app/migrations
COPY --chown=appuser:appuser frontend /app/frontend
COPY --chown=appuser:appuser alembic.ini pyproject.toml /app/
COPY --chown=appuser:appuser scripts/entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

# Zmienne środowiskowe
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SQLITE_DB_PATH="/app/data/movie_recommend.db"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3. Skrypt startowy `entrypoint.sh`

Skrypt automatycznie wykonuje migracje bazy danych przed startem aplikacji, gwarantując bezobsługowe aktualizacje:

```bash
#!/usr/bin/env bash
set -e

echo "[entrypoint] Uruchamianie aplikacji w kontenerze..."

# Sprawdzenie możliwości zapisu do katalogu bazy
DATA_DIR=$(dirname "${SQLITE_DB_PATH:-/app/data/movie_recommend.db}")
if [ ! -w "$DATA_DIR" ]; then
    echo "[entrypoint] BŁĄD: Brak uprawnień do zapisu w katalogu $DATA_DIR!"
    echo "[entrypoint] Upewnij się, że na hoście katalog ma uprawnienia UID 1000."
    exit 1
fi

# Automatyczna migracja schematu Alembic
echo "[entrypoint] Sprawdzanie i aplikowanie migracji bazy danych..."
python -m alembic upgrade head
echo "[entrypoint] Migracje zakończone pomyślnie."

# Przekazanie kontroli do uvicorn (CMD)
exec "$@"
```

---

## 4. Konfiguracja `docker-compose.yml`

```yaml
version: "3.8"

services:
  curato:
    build:
      context: .
      dockerfile: Dockerfile
    image: curato:latest
    container_name: curato
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - SQLITE_DB_PATH=/app/data/movie_recommend.db
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')\" || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

---

## 5. Konfiguracja Reverse Proxy dla MCP SSE (ChatGPT)

ChatGPT wymaga publicznego adresu HTTPS z poprawnym certyfikatem SSL oraz stabilnego transportu Server-Sent Events (SSE) pod adresem `/mcp/sse`. Domyślne proxy buforuje pakiety, co zrywa strumień SSE.

### Wariant A: Caddy (Caddyfile) — Rekomendowany

Caddy domyślnie dobrze radzi sobie ze strumieniowaniem, z wyłączeniem buforowania:

```caddy
curato.twoja-domena.pl {
    reverse_proxy 127.0.0.1:8000 {
        flush_interval -1
    }
}
```

### Wariant B: Nginx / Nginx Proxy Manager

W konfiguracji lokalizacji serwera Nginx dla endpointów MCP:

```nginx
# Konfiguracja dla SSE MCP
location /mcp/ {
    proxy_pass http://127.0.0.1:8000/mcp/;
    proxy_http_version 1.1;

    # Wyłączenie buforowania pod kątem SSE
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_set_header X-Accel-Buffering no;
    
    # Przekazywanie nagłówków
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Dłuższe timeouty dla połączeń asynchronicznych MCP
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

# Domyślna konfiguracja dla API i UI
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 6. Procedura wdrożenia w Proxmox VE (LXC)

1. **Utworzenie kontenera LXC**:
   - Szablon: Debian 12 (Bookworm) standard.
   - Pamięć: 1-2 GB RAM, 2 rdzenie CPU, dysk 10-20 GB.
   - Opcje: Nesting włączony (`features: nesting=1,keyctl=1`) dla obsługi Dockera.
2. **Klonowanie repozytorium i uprawnienia bazy**:
   ```bash
   git clone <repo_url> /opt/curato
   cd /opt/curato
   cp .env.example .env
   # Wypełnij klucze w .env (SIMKL, TMDB, GEMINI, MCP_API_KEY)
   mkdir -p data
   sudo chown -R 1000:1000 data
   sudo chmod 775 data
   ```
3. **Uruchomienie i weryfikacja**:
   ```bash
   docker compose up -d --build
   docker compose logs -f
   curl http://localhost:8000/api/health
   ```
4. **Kopie zapasowe (Proxmox Backup Server / VZDump)**:
   - Dzięki umieszczeniu bazy w trybie WAL na wolumenie hosta LXC, standardowy backup Proxmox (tryb `snapshot`) wykonuje w 100% spójną kopię zapasową całego kontenera wraz z bazą.
