import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.settings import AppSetting

logger = logging.getLogger(__name__)

SIMKL_TOKENS_SETTING_KEY = "simkl_auth_tokens"


def get_stored_simkl_tokens(db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves persisted Simkl OAuth tokens from the app_settings table.
    Returns a dict with 'access_token', 'refresh_token', 'expires_at' or None.
    """

    def _query(s: Session) -> Optional[Dict[str, Any]]:
        record = s.scalar(select(AppSetting).where(AppSetting.key == SIMKL_TOKENS_SETTING_KEY))
        if record and record.value_json:
            try:
                data = json.loads(record.value_json)
                if isinstance(data, dict) and data.get("access_token"):
                    return data
            except Exception as e:
                logger.warning("Failed to parse stored Simkl tokens from app_settings: %s", e)
        return None

    try:
        if db is not None:
            return _query(db)
        with SessionLocal() as session:
            return _query(session)
    except Exception as e:
        logger.debug("Could not read Simkl tokens from database: %s", e)
        return None


def save_stored_simkl_tokens(
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,
    db: Optional[Session] = None,
) -> None:
    """
    Saves or updates Simkl OAuth tokens in the app_settings table in a short transaction.
    """
    expires_at = time.time() + expires_in if expires_in else None
    token_payload: Dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    def _save(s: Session) -> None:
        record = s.scalar(select(AppSetting).where(AppSetting.key == SIMKL_TOKENS_SETTING_KEY))
        if not record:
            record = AppSetting(
                key=SIMKL_TOKENS_SETTING_KEY,
                value_json=json.dumps(token_payload),
            )
            s.add(record)
        else:
            # Preserve existing refresh_token if new one was not returned in response
            if not refresh_token and record.value_json:
                try:
                    old_data = json.loads(record.value_json)
                    if isinstance(old_data, dict) and old_data.get("refresh_token"):
                        token_payload["refresh_token"] = old_data["refresh_token"]
                except Exception:
                    pass
            record.value_json = json.dumps(token_payload)
        s.commit()

    try:
        if db is not None:
            _save(db)
        else:
            with SessionLocal() as session:
                _save(session)
        logger.info("Successfully persisted updated Simkl tokens to database.")
    except Exception as e:
        logger.warning("Failed to save Simkl tokens to database: %s", e)

    # Also attempt updating .env file if writable (e.g., local development)
    try_update_env_tokens(access_token, token_payload.get("refresh_token"))


def try_update_env_tokens(access_token: str, refresh_token: Optional[str] = None) -> None:
    """
    Attempts to update local .env file with new SIMKL_USER_TOKEN and SIMKL_REFRESH_TOKEN.
    Fails silently if .env is missing or unwritable (e.g., inside Docker container).
    """
    env_path = Path(".env")
    if not env_path.exists() or not os.access(env_path, os.W_OK):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        updates: Dict[str, str] = {"SIMKL_USER_TOKEN": access_token}
        if refresh_token:
            updates["SIMKL_REFRESH_TOKEN"] = refresh_token

        new_lines = []
        keys_updated = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _ = stripped.split("=", 1)
                k = k.strip()
                if k in updates:
                    new_lines.append(f"{k}={updates[k]}\n")
                    keys_updated.add(k)
                    continue
            new_lines.append(line)

        for k, v in updates.items():
            if k not in keys_updated:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        logger.debug("Updated .env file with latest Simkl tokens.")
    except Exception as e:
        logger.debug("Could not write updated tokens to .env: %s", e)
