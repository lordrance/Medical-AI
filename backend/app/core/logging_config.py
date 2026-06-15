from __future__ import annotations

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import TimeStamper, JSONRenderer

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure structlog once at application startup.

    In development mode we use a pretty console renderer so lines are
    easy to read during local testing.  In production / test we output
    JSON so log aggregators can parse them.
    """
    settings = get_settings()
    is_dev = settings.APP_ENV == "development"

    processors = [
        structlog.stdlib.add_log_level,
        structlog.dev.set_exc_info,
        structlog.contextvars.merge_contextvars,
    ]

    if is_dev:
        processors.extend(
            [
                TimeStamper(fmt="iso", utc=True),
                ConsoleRenderer(),
            ]
        )
    else:
        processors.extend(
            [
                TimeStamper(fmt="iso", utc=True),
                JSONRenderer(),
            ]
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
