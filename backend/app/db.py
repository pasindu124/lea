"""Thin PostgreSQL helper (psycopg 3 + connection pool). Plain SQL, dict rows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

_pool: ConnectionPool | None = None
SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=8,
                               kwargs={"row_factory": dict_row}, open=True)
    return _pool


def reset_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def query(sql: str, params: Iterable[Any] | dict | None = None) -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


def query_one(sql: str, params: Iterable[Any] | dict | None = None) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] | dict | None = None) -> None:
    with get_pool().connection() as conn:
        conn.execute(sql, params)


def apply_schema() -> None:
    with get_pool().connection() as conn:
        conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))


def get_meta(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM meta WHERE key = %s", (key,))
    return row["value"] if row else default


def set_meta(key: str, value: Any) -> None:
    execute(
        "INSERT INTO meta (key, value) VALUES (%s, %s::jsonb) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (key, json.dumps(value, default=str)),
    )
