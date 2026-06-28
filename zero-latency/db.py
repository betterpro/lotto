"""Tiny async database layer that works with either SQLite (default, zero-setup)
or Postgres (set DATABASE_URL=postgres://…).

Queries are written with ``?`` placeholders; for Postgres they're rewritten to
``$1, $2, …``. Rows come back as plain dicts. Timestamps are written from Python
(UTC ISO-8601, second precision) so the SQL stays dialect-neutral.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import config

_IS_PG = config.DATABASE_URL.startswith(("postgres://", "postgresql://"))


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _sqlite_path() -> str:
    # sqlite:///./bookings.db  ->  ./bookings.db
    url = config.DATABASE_URL
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):]
    return url


def _to_pg(sql: str) -> str:
    idx = 0

    def repl(_m):
        nonlocal idx
        idx += 1
        return f"${idx}"

    return re.sub(r"\?", repl, sql)


_ID_COL = "BIGSERIAL PRIMARY KEY" if _IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS bookings (
    id              {_ID_COL},
    ref             TEXT UNIQUE NOT NULL,
    venue_id        TEXT NOT NULL,
    experience_id   TEXT NOT NULL,
    experience_name TEXT NOT NULL,
    slot_date       TEXT NOT NULL,
    slot_time       TEXT NOT NULL,
    players         INTEGER NOT NULL,
    unit_price      INTEGER NOT NULL,
    amount          INTEGER NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'CAD',
    customer_name   TEXT NOT NULL,
    customer_email  TEXT NOT NULL,
    customer_phone  TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    stripe_session_id     TEXT,
    stripe_payment_intent TEXT,
    created_at      TEXT NOT NULL,
    confirmed_at    TEXT
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings (experience_id, slot_date, slot_time)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings (status)",
]

_pool = None  # asyncpg pool when in Postgres mode


async def init() -> None:
    """Create the connection pool (Postgres) and apply the schema."""
    global _pool
    if _IS_PG:
        import asyncpg
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
        async with _pool.acquire() as con:
            await con.execute(_SCHEMA)
            for stmt in _INDEXES:
                await con.execute(stmt)
    else:
        import aiosqlite
        async with aiosqlite.connect(_sqlite_path()) as con:
            await con.execute(_SCHEMA)
            for stmt in _INDEXES:
                await con.execute(stmt)
            await con.commit()


async def execute(sql: str, params: tuple = ()) -> None:
    if _IS_PG:
        async with _pool.acquire() as con:
            await con.execute(_to_pg(sql), *params)
    else:
        import aiosqlite
        async with aiosqlite.connect(_sqlite_path()) as con:
            await con.execute(sql, params)
            await con.commit()


async def fetchone(sql: str, params: tuple = ()) -> dict | None:
    rows = await fetchall(sql, params)
    return rows[0] if rows else None


async def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    if _IS_PG:
        async with _pool.acquire() as con:
            rows = await con.fetch(_to_pg(sql), *params)
            return [dict(r) for r in rows]
    else:
        import aiosqlite
        async with aiosqlite.connect(_sqlite_path()) as con:
            con.row_factory = aiosqlite.Row
            cur = await con.execute(sql, params)
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def close() -> None:
    if _IS_PG and _pool is not None:
        await _pool.close()
