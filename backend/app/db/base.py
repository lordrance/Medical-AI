from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Async-friendly declarative base."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
