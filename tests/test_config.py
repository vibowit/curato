from pydantic import SecretStr

from app.core.config import Settings


def test_default_settings():
    settings = Settings(
        DATABASE_URL="sqlite:///data/test.db",
        _env_file=None,
    )
    assert settings.PROJECT_NAME == "Movie & Show Recommendation System"
    assert settings.ENVIRONMENT in ["development", "test", "production"]
    assert settings.is_sqlite is True
    assert settings.DATABASE_URL == "sqlite:///data/test.db"


def test_secrets_masking():
    settings = Settings(
        SIMKL_CLIENT_ID=SecretStr("my_simkl_id"),
        SIMKL_CLIENT_SECRET=SecretStr("my_secret_token"),
        GEMINI_API_KEY=SecretStr("ai_key_123"),
        _env_file=None,
    )
    # Ensure raw secret string is not in repr
    repr_str = repr(settings)
    assert "my_simkl_id" not in repr_str
    assert "my_secret_token" not in repr_str
    assert "ai_key_123" not in repr_str

    # But secret can be retrieved explicitly when needed
    assert settings.SIMKL_CLIENT_SECRET.get_secret_value() == "my_secret_token"
