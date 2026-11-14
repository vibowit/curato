from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings validated with Pydantic Settings."""

    PROJECT_NAME: str = "Movie & Show Recommendation System"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite:///data/movie_recommend.db"

    # Simkl Integration
    SIMKL_CLIENT_ID: SecretStr | None = None
    SIMKL_CLIENT_SECRET: SecretStr | None = None
    SIMKL_ACCESS_TOKEN: SecretStr | None = None
    SIMKL_USER_TOKEN: SecretStr | None = None
    SIMKL_USERNAME: str | None = None
    SIMKL_BASE_URL: str = "https://api.simkl.com"
    SIMKL_TIMEOUT_SECONDS: float = 15.0

    @property
    def effective_simkl_token(self) -> SecretStr | None:
        """Returns SIMKL_USER_TOKEN if set, otherwise SIMKL_ACCESS_TOKEN."""
        return self.SIMKL_USER_TOKEN or self.SIMKL_ACCESS_TOKEN

    # LLM Providers
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str | None = None
    OPENAI_API_KEY: SecretStr | None = None

    # TMDB Integration
    TMDB_API_KEY: SecretStr | None = None
    TMDB_READ_ACCESS_TOKEN: SecretStr | None = None

    # MCP & Scheduler
    MCP_SERVER_NAME: str = "movie-recommend"
    MCP_API_KEY: SecretStr | None = None
    SCHEDULER_ENABLED: bool = False
    SCHEDULER_INTERVAL_HOURS: int = 168
    SCHEDULER_RUN_ON_STARTUP: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    def ensure_data_dir(self) -> None:
        """Ensure the local directory for sqlite or data storage exists."""
        if self.is_sqlite:
            # Strip sqlite:/// or sqlite:////
            clean_path = self.DATABASE_URL.replace("sqlite:///", "")
            if clean_path and clean_path != ":memory:":
                db_file = Path(clean_path)
                db_file.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
