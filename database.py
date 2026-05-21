"""
SQLite database layer — all I/O is async via aiosqlite.

Tables
------
users           – registered members
rounds          – weekly lottery rounds
participations  – each member's stake in a round
transactions    – credit ledger (deposit / withdraw / participate / win)
deposit_requests – pending deposits awaiting trustee approval
"""

import aiosqlite
from datetime import datetime
from config import DB_PATH

# ──────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    telegram_id   INTEGER PRIMARY KEY,
    username      TEXT,
    full_name     TEXT    NOT NULL,
    credit        REAL    NOT NULL DEFAULT 0,
    is_trustee    INTEGER NOT NULL DEFAULT 0,
    invited_by    INTEGER REFERENCES users(telegram_id),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rounds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    status        TEXT    NOT NULL DEFAULT 'open',   -- open | closed | drawn
    pool          REAL    NOT NULL DEFAULT 0,
    winner_id     INTEGER REFERENCES users(telegram_id),
    ticket_ref    TEXT,                               -- external lottery ticket number / ref
    opened_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    closed_at     TEXT,
    drawn_at      TEXT
);

CREATE TABLE IF NOT EXISTS participations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id      INTEGER NOT NULL REFERENCES rounds(id),
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    amount        REAL    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(round_id, user_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    type          TEXT    NOT NULL,   -- deposit | withdraw | participate | win | refund
    amount        REAL    NOT NULL,
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deposit_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    amount        REAL    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    trustee_note  TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at   TEXT
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    return db


# ──────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────

async def get_user(db: aiosqlite.Connection, telegram_id: int):
    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        return await cur.fetchone()


async def create_user(db: aiosqlite.Connection, telegram_id: int,
                      username: str | None, full_name: str,
                      invited_by: int | None = None, is_trustee: int = 0):
    await db.execute(
        """INSERT OR IGNORE INTO users
           (telegram_id, username, full_name, invited_by, is_trustee)
           VALUES (?, ?, ?, ?, ?)""",
        (telegram_id, username, full_name, invited_by, is_trustee),
    )
    await db.commit()


async def update_credit(db: aiosqlite.Connection, telegram_id: int, delta: float):
    await db.execute(
        "UPDATE users SET credit = credit + ? WHERE telegram_id = ?",
        (delta, telegram_id),
    )
    await db.commit()


async def all_users(db: aiosqlite.Connection):
    async with db.execute("SELECT * FROM users ORDER BY created_at") as cur:
        return await cur.fetchall()


# ──────────────────────────────────────────────
# Rounds
# ──────────────────────────────────────────────

async def get_open_round(db: aiosqlite.Connection):
    async with db.execute(
        "SELECT * FROM rounds WHERE status = 'open' ORDER BY id DESC LIMIT 1"
    ) as cur:
        return await cur.fetchone()


async def get_round(db: aiosqlite.Connection, round_id: int):
    async with db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)) as cur:
        return await cur.fetchone()


async def create_round(db: aiosqlite.Connection) -> int:
    async with db.execute(
        "INSERT INTO rounds (status) VALUES ('open')"
    ) as cur:
        await db.commit()
        return cur.lastrowid


async def close_round(db: aiosqlite.Connection, round_id: int):
    await db.execute(
        "UPDATE rounds SET status='closed', closed_at=datetime('now') WHERE id=?",
        (round_id,),
    )
    await db.commit()


async def set_round_winner(db: aiosqlite.Connection, round_id: int,
                           winner_id: int, ticket_ref: str | None):
    await db.execute(
        """UPDATE rounds
           SET status='drawn', winner_id=?, ticket_ref=?, drawn_at=datetime('now')
           WHERE id=?""",
        (winner_id, ticket_ref, round_id),
    )
    await db.commit()


async def recent_rounds(db: aiosqlite.Connection, limit: int = 10):
    async with db.execute(
        "SELECT * FROM rounds ORDER BY id DESC LIMIT ?", (limit,)
    ) as cur:
        return await cur.fetchall()


# ──────────────────────────────────────────────
# Participations
# ──────────────────────────────────────────────

async def get_participation(db: aiosqlite.Connection, round_id: int, user_id: int):
    async with db.execute(
        "SELECT * FROM participations WHERE round_id=? AND user_id=?",
        (round_id, user_id),
    ) as cur:
        return await cur.fetchone()


async def upsert_participation(db: aiosqlite.Connection, round_id: int,
                               user_id: int, additional: float):
    """Add to existing stake or create new row; also update round pool."""
    existing = await get_participation(db, round_id, user_id)
    if existing:
        await db.execute(
            "UPDATE participations SET amount=amount+? WHERE round_id=? AND user_id=?",
            (additional, round_id, user_id),
        )
    else:
        await db.execute(
            "INSERT INTO participations (round_id, user_id, amount) VALUES (?,?,?)",
            (round_id, user_id, additional),
        )
    await db.execute(
        "UPDATE rounds SET pool=pool+? WHERE id=?", (additional, round_id)
    )
    await db.commit()


async def round_participations(db: aiosqlite.Connection, round_id: int):
    async with db.execute(
        """SELECT p.*, u.full_name, u.username
           FROM participations p
           JOIN users u ON u.telegram_id = p.user_id
           WHERE p.round_id = ?
           ORDER BY p.amount DESC""",
        (round_id,),
    ) as cur:
        return await cur.fetchall()


async def user_participations(db: aiosqlite.Connection, user_id: int, limit: int = 10):
    async with db.execute(
        """SELECT p.*, r.status, r.pool, r.winner_id, r.drawn_at
           FROM participations p
           JOIN rounds r ON r.id = p.round_id
           WHERE p.user_id = ?
           ORDER BY p.round_id DESC
           LIMIT ?""",
        (user_id, limit),
    ) as cur:
        return await cur.fetchall()


# ──────────────────────────────────────────────
# Transactions
# ──────────────────────────────────────────────

async def add_transaction(db: aiosqlite.Connection, user_id: int,
                          tx_type: str, amount: float, note: str | None = None):
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (user_id, tx_type, amount, note),
    )
    await db.commit()


async def user_transactions(db: aiosqlite.Connection, user_id: int, limit: int = 15):
    async with db.execute(
        """SELECT * FROM transactions WHERE user_id=?
           ORDER BY created_at DESC LIMIT ?""",
        (user_id, limit),
    ) as cur:
        return await cur.fetchall()


# ──────────────────────────────────────────────
# Deposit requests
# ──────────────────────────────────────────────

async def create_deposit_request(db: aiosqlite.Connection,
                                 user_id: int, amount: float) -> int:
    async with db.execute(
        "INSERT INTO deposit_requests (user_id, amount) VALUES (?,?)",
        (user_id, amount),
    ) as cur:
        await db.commit()
        return cur.lastrowid


async def get_deposit_request(db: aiosqlite.Connection, req_id: int):
    async with db.execute(
        "SELECT * FROM deposit_requests WHERE id=?", (req_id,)
    ) as cur:
        return await cur.fetchone()


async def resolve_deposit(db: aiosqlite.Connection, req_id: int,
                          status: str, note: str | None = None):
    await db.execute(
        """UPDATE deposit_requests
           SET status=?, trustee_note=?, resolved_at=datetime('now')
           WHERE id=?""",
        (status, note, req_id),
    )
    await db.commit()


async def pending_deposits(db: aiosqlite.Connection):
    async with db.execute(
        """SELECT dr.*, u.full_name, u.username
           FROM deposit_requests dr
           JOIN users u ON u.telegram_id = dr.user_id
           WHERE dr.status='pending'
           ORDER BY dr.created_at""",
    ) as cur:
        return await cur.fetchall()
