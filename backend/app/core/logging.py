"""Structured logging configuration for the backend.

Sets up structlog with the "render-to-JSON" pipeline so every log call
produces a JSON line to stdout, which Docker / journald collect. We also
configure the standard-library `logging` bridge so libraries that use
`logging.getLogger()` (uvicorn, sqlalchemy, alembic) are routed through
structlog with the right keys.

Usage:
    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("request_ok", path="/healthz", status=200, duration_ms=1.2)
"""

from __future__ import annotations

import logging
import structlog
from structlog.typing import Processor


def _drop_null_keys(_logger: Any, _method: str, event_dict: dict) -> dict:
    """Remove keys whose value is None so logs stay dense."""
    return {k: v for k, v in event_dict.items() if v is not None}


def configure() -> None:
    """Call once at app startup."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # so request_id appears
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _drop_null_keys,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge: anything that calls logging.getLogger() (uvicorn, alembic,
    # sqlalchemy, etc.) gets rendered as structured JSON too.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
