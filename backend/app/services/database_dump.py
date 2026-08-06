"""
================================================================================
文件作用：整库导出 —— 把整个数据库打包成一个能还原的文件
================================================================================

后台「导出完整数据库」按钮背后就是这个文件。导出的文件是一份完整快照，
拿着它可以在任何一台机器上还原出一模一样的数据库。

★ 这是最保险的备份方式，比导出 CSV 完整得多：CSV 只有数据，
  整库导出连表结构、索引、约束都带着。

两种数据库两种做法：
  SQLite（本地开发）  用 Python 内置的 iterdump()，纯文本 SQL
  Postgres（生产）    调用系统上的 pg_dump 命令行工具

★ 注意：这个函数是**阻塞式**的（pg_dump 是外部进程，要等它跑完）。
  调用方必须用 run_in_threadpool 把它挪到独立线程里跑，
  否则会把整个 worker 卡住，所有医生的请求一起卡死
  （见 api/admin/export.py，那里有详细说明）。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  full_database_dump_bytes()  ★ 入口：看是哪种数据库，分发给下面
  第 2 块  _db_path_from_sqlite_url()  从连接串里解析出 SQLite 文件路径
  第 3 块  _sqlite_sql_dump()          SQLite 的导出
  第 4 块  _sync_url_for_pg_dump()     把连接串转成 pg_dump 认的格式
  第 5 块  _postgres_pg_dump()         ★ Postgres 的导出（生产环境走这条）
================================================================================
"""

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


# ── 第 1 块：入口，按数据库类型分发 ★ ────────────────────────────────────
def full_database_dump_bytes() -> tuple[bytes, str, str]:
    """Return (bytes, filename, media_type) for download.

    SQLite: textual SQL via sqlite3.Connection.iterdump() (portable).
    PostgreSQL: binary output from pg_dump -Fc or plain SQL via pg_dump --plain.

    Raises RuntimeError if dump cannot be produced (with human-readable message).
    """
    settings = get_settings()
    url = make_url(settings.DATABASE_URL)

    # drivername 是连接串开头那段，比如 "postgresql+asyncpg" 或 "sqlite+aiosqlite"。
    driver = url.drivername or ""
    if driver.startswith("sqlite"):
        return _sqlite_sql_dump(url)

    if "postgresql" in driver or "postgres" in driver:
        return _postgres_pg_dump(url)

    raise RuntimeError(
        f"Unsupported DATABASE_URL driver for full dump: {driver}. "
        "Use SQLite or PostgreSQL."
    )


# ── 第 2 块：解析 SQLite 文件路径 ─────────────────────────────────────────
def _db_path_from_sqlite_url(url) -> Path:
    """从连接串里取出数据库文件的绝对路径。"""
    database = url.database
    if not database:
        raise RuntimeError("SQLite DATABASE_URL has no database path")
    p = Path(database)
    # 连接串里可能写的是相对路径（如 ./dev.db），转成绝对路径，
    # 这样无论程序从哪个目录启动都能找到文件。
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()   # resolve 会把 .. 和符号链接都展开


# ── 第 3 块：SQLite 导出 ──────────────────────────────────────────────────
def _sqlite_sql_dump(url) -> tuple[bytes, str, str]:
    """把 SQLite 数据库导成一串 SQL 语句。只在本地开发时会走到。"""
    path = _db_path_from_sqlite_url(url)
    if not path.is_file():
        raise RuntimeError(f"SQLite database file not found: {path}")

    conn = sqlite3.connect(str(path))
    try:
        # iterdump() 一行一行地吐出还原这个数据库所需的全部 SQL 语句。
        # StringIO 是内存里的"假文件"，用来把这些行拼成一整个字符串。
        buf = io.StringIO()
        for line in conn.iterdump():
            buf.write(line)
        sql = buf.getvalue()
    finally:
        # ★ finally 保证即使中间出错也会关掉连接，不留下野连接。
        conn.close()

    name = f"{path.stem}_full_dump.sql"
    return sql.encode("utf-8"), name, "application/sql; charset=utf-8"


# ── 第 4 块：连接串格式转换 ──────────────────────────────────────────────
def _sync_url_for_pg_dump(url) -> str:
    """Build libpq-style URI for pg_dump.

    我们程序里用的连接串是 postgresql+asyncpg://... 这种带驱动名的格式，
    但 pg_dump 是个独立的命令行工具，只认标准的 postgresql://... 格式。
    这个函数负责翻译。
    """
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


# ── 第 5 块：Postgres 导出 ★ 生产环境走这条 ──────────────────────────────
def _postgres_pg_dump(url) -> tuple[bytes, str, str]:
    """调用系统上的 pg_dump 命令导出整库。"""
    # shutil.which 相当于命令行的 which：找这个命令在不在系统里。
    # 找不到就明确报错，而不是让 subprocess 抛一个看不懂的异常。
    if shutil.which("pg_dump") is None:
        raise RuntimeError(
            "pg_dump not found in PATH. Install PostgreSQL client tools on the server "
            "or use SQLite for development dumps."
        )

    uri = _sync_url_for_pg_dump(url)
    env = os.environ.copy()
    # pg_dump URI may embed password; avoid logging uri
    # ★ 连接串里带着数据库密码，所以绝对不能把 uri 打进日志。
    #   下面出错时只记 stderr，不记这个变量。
    proc = subprocess.run(
        [
            # ★ 命令和参数写成列表，不是拼成一个字符串。
            #   拼字符串的话密码里如果有特殊字符会被 shell 解释，
            #   既可能出错也可能被注入命令。列表形式直接传给系统，绝对安全。
            "pg_dump",
            "--no-owner",     # 不导出"属主是谁"，还原到别的机器上才不会报错
            "--no-acl",       # 同理，不导出权限设置
            "--clean",        # 还原前先删掉同名的表
            "--if-exists",    # 配合 --clean：表不存在时也不报错
            uri,
        ],
        capture_output=True,  # 把输出抓到内存里，而不是打到屏幕
        env=env,
        timeout=600,          # 10 分钟还没跑完就放弃，防止无限期挂住
    )
    # 返回码 0 表示成功，非 0 表示出错。
    if proc.returncode != 0:
        # 只取前 2000 字符：错误信息可能极长，日志会被刷爆。
        # errors="replace" 表示遇到解不了码的字节就用替代字符顶上，不抛异常。
        err = proc.stderr.decode("utf-8", errors="replace")[:2000]
        logger.warning("pg_dump failed: %s", err)
        raise RuntimeError(f"pg_dump failed (exit {proc.returncode}): {err}")

    dbname = url.database or "database"
    filename = f"{dbname}_full_dump.sql"
    return proc.stdout, filename, "application/sql; charset=utf-8"
