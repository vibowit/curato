#!/usr/bin/env bash
set -e

echo "[entrypoint] Uruchamianie Curato w kontenerze..."

# Weryfikacja praw do zapisu w katalogu bazy (SQLite WAL)
DATA_DIR=$(dirname "${SQLITE_DB_PATH:-/app/data/movie_recommend.db}")
if [ ! -w "$DATA_DIR" ]; then
    echo "[entrypoint] BŁĄD: Brak uprawnień do zapisu w katalogu $DATA_DIR!"
    echo "[entrypoint] Upewnij się, że katalog na hoście ma uprawnienia zapisu dla UID 1000."
    exit 1
fi

# Automatyczna migracja schematu bazy danych
echo "[entrypoint] Wykonywanie migracji bazy danych Alembic..."
python -m alembic upgrade head
echo "[entrypoint] Migracje zakończone pomyślnie."

# Uruchomienie aplikacji przekazanej w CMD
exec "$@"
