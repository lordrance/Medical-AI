"""Full-database export helpers (SQLite SQL dump or PostgreSQL pg_dump)."""

from __future__ import annotations

import io
import logging
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

from sqlalchemy.engine.url import make_url

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def full_database_dump_bytes() -> tuple[bytes, str, str]:
    """Return (bytes, filename, media_type) for download.

    SQLite: textual SQL via sqlite3.Connection.iterdump() (portable).
    PostgreSQL: binary output from pg_dump -Fc or plain SQL via pg_dump --plain.

    Raises RuntimeError if dump cannot be produced (with human-readable message).
    """
    settings = get_settings()
    url = make_url(settings.DATABASE_URL)

    driver = url.drivername or ""
    if driver.startswith("sqlite"):
        return _sqlite_sql_dump(url)

    if "postgresql" in driver or "postgres" in driver:
        return _postgres_pg_dump(url)

    raise RuntimeError(
        f"Unsupported DATABASE_URL driver for full dump: {driver}. "
        "Use SQLite or PostgreSQL."
    )


def _db_path_from_sqlite_url(url) -> Path:
    database = url.database
    if not database:
        raise RuntimeError("SQLite DATABASE_URL has no database path")
    p = Path(database)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def _sqlite_sql_dump(url) -> tuple[bytes, str, str]:
    path = _db_path_from_sqlite_url(url)
    if not path.is_file():
        raise RuntimeError(f"SQLite database file not found: {path}")

    conn = sqlite3.connect(str(path))
    try:
        buf = io.StringIO()
        for line in conn.iterdump():
            buf.write(line)
        sql = buf.getvalue()
    finally:
        conn.close()

    name = f"{path.stem}_full_dump.sql"
    return sql.encode("utf-8"), name, "application/sql; charset=utf-8"


def _sync_url_for_pg_dump(url) -> str:
    """Build libpq-style URI for pg_dump."""
    user = url.username or ""
    password = url.password or ""
    host = url.host or "localhost"
    port = url.port or 5432
    db = url.database or ""
    auth = ""
    if user:
        auth = user
        if password:
            auth += f":{password}"
        auth += "@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def _postgres_pg_dump(url) -> tuple[bytes, str, str]:
    if shutil.which("pg_dump") is None:
        raise RuntimeError(
            "pg_dump not found in PATH. Install PostgreSQL client tools on the server "
            "or use SQLite for development dumps."
        )

    uri = _sync_url_for_pg_dump(url)
    env = os.environ.copy()
    # pg_dump URI may embed password; avoid logging uri
    proc = subprocess.run(
        [
            "pg_dump",
            "--no-owner",
            "--no-acl",
            "--clean",
            "--if-exists",
            uri,
        ],
        capture_output=True,
        env=env,
        timeout=600,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[:2000]
        logger.warning("pg_dump failed: %s", err)
        raise RuntimeError(f"pg_dump failed (exit {proc.returncode}): {err}")

    dbname = url.database or "database"
    filename = f"{dbname}_full_dump.sql"
    return proc.stdout, filename, "application/sql; charset=utf-8"
