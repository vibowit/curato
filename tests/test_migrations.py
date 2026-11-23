import os
import tempfile

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_and_downgrade():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_migration.db")
        db_url = f"sqlite:///{db_path}"

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # Run upgrade head
        command.upgrade(alembic_cfg, "head")

        # Verify tables exist
        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected_tables = {
            "app_settings",
            "media_items",
            "watch_history",
            "taste_profiles",
            "recommendation_runs",
            "recommendations",
            "user_decisions",
            "sync_state",
            "alembic_version",
        }
        assert expected_tables.issubset(tables)

        # Run downgrade base
        command.downgrade(alembic_cfg, "base")

        # Verify tables are dropped
        inspector_after = inspect(engine)
        tables_after = set(inspector_after.get_table_names())
        assert "media_items" not in tables_after
        assert "recommendations" not in tables_after


def test_alembic_uses_settings_database_url(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "dynamic_settings.db")
        db_url = f"sqlite:///{db_path}"

        from app.core.config import settings

        monkeypatch.setattr(settings, "DATABASE_URL", db_url)

        # Config initialized from alembic.ini without explicit sqlalchemy.url
        alembic_cfg = Config("alembic.ini")

        command.upgrade(alembic_cfg, "head")

        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "sync_state" in tables
        assert "media_items" in tables
