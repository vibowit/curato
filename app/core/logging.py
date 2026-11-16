import logging
import sys

from app.core.config import settings


class RedactingFilter(logging.Filter):
    """Filter that obscures sensitive token-like strings in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            # Check known secrets if configured
            for secret_attr in [
                settings.SIMKL_ACCESS_TOKEN,
                settings.SIMKL_CLIENT_SECRET,
                settings.GEMINI_API_KEY,
                settings.TMDB_API_KEY,
                settings.TMDB_READ_ACCESS_TOKEN,
            ]:
                if secret_attr is not None:
                    secret_val = secret_attr.get_secret_value()
                    if secret_val and len(secret_val) > 4:
                        record.msg = record.msg.replace(secret_val, "***REDACTED***")
        return True


def setup_logging() -> None:
    """Configure structured console logging with redaction."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(log_level)
            handler.addFilter(RedactingFilter())
