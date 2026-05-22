"""
SQLite database layer — all I/O is async via aiosqlite.
"""

import aiosqlite
from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    telegram_id        INTEGER PRIMARY KEY,
    username           TEXT,
    full_name          TEXT    NOT NULL,
    credit             REAL    NOT NULL DEFAULT 0,
    is_trustee         INTEGER NOT NULL DEFAULT 0,
    invited_by         INTEGER REFERENCES users(telegram_id),
    stripe_customer_id TEXT,
    photo_url          TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id              INTEGER PRIMARY KEY REFERENCES users(telegram_id),
    auto_participate     INTEGER NOT NULL DEFAULT 0,
    shares_per_round     INTEGER NOT NULL DEFAULT 1,
    max_rounds_per_month INTEGER NOT NULL DEFAULT 4,
    preferred_day        INTEGER,
    notif_new_round      INTEGER NOT NULL DEFAULT 1,
    notif_reminder       INTEGER NOT NULL DEFAULT 1,
    notif_ticket         INTEGER NOT NULL DEFAULT 1,
    notif_results        INTEGER NOT NULL DEFAULT 1,
    updated_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rounds (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    status           TEXT    NOT NULL DEFAULT 'open',
    pool             REAL    NOT NULL DEFAULT 0,
    draw_date        TEXT,
    winner_id        INTEGER REFERENCES users(telegram_id),
    ticket_ref       TEXT,
    opened_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    closed_at        TEXT,
    drawn_at         TEXT,
    jackpot          INTEGER DEFAULT 0,
    tickets_target   INTEGER DEFAULT 25,
    price_per_share  REAL    DEFAULT 5,
    winning_numbers  TEXT,
    bonus_number     INTEGER,
    ticket_numbers   TEXT
);

CREATE TABLE IF NOT EXISTS participations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id      INTEGER NOT NULL REFERENCES rounds(id),
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    amount        REAL    NOT NULL,
    shares        INTEGER DEFAULT 1,
    prize         REAL    DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(round_id, user_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    type          TEXT    NOT NULL,
    amount        REAL    NOT NULL,
    note          TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deposit_requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    amount        REAL    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    trustee_note  TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    resolved_at   TEXT
);

CREATE TABLE IF NOT EXISTS stripe_subscriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(telegram_id),
    stripe_sub_id TEXT    NOT NULL UNIQUE,
    amount        REAL    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'active',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    for col_sql in [
        "ALTER TABLE rounds ADD COLUMN draw_date TEXT",
        "ALTER TABLE users  ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE rounds ADD COLUMN jackpot INTEGER DEFAULT 0",
        "ALTER TABLE rounds ADD COLUMN tickets_target INTEGER DEFAULT 25",
        "ALTER TABLE rounds ADD COLUMN price_per_share REAL DEFAULT 5",
        "ALTER TABLE rounds ADD COLUMN winning_numbers TEXT",
        "ALTER TABLE rounds ADD COLUMN bonus_number INTEGER",
        "ALTER TABLE rounds ADD COLUMN ticket_numbers TEXT",
        "ALTER TABLE participations ADD COLUMN shares INTEGER DEFAULT 1",
        "ALTER TABLE participations ADD COLUMN prize REAL DEFAULT 0",
        "ALTER TABLE rounds ADD COLUMN ticket_image TEXT",
        "ALTER TABLE users  ADD COLUMN photo_url TEXT",
    ]:
        try:
            await db.execute(col_sql)
            await db.commit()
        except Exception:
            pass
    return db


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user(db, telegram_id):
    async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as c:
        return await c.fetchone()

async def create_user(db, telegram_id, username, full_name, invited_by=None, is_trustee=0):
    await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, full_name, invited_by, is_trustee) VALUES (?,?,?,?,?)",
        (telegram_id, username, full_name, invited_by, is_trustee))
    await db.commit()

async def update_credit(db, telegram_id, delta):
    await db.execute("UPDATE users SET credit = credit + ? WHERE telegram_id = ?", (delta, telegram_id))
    await db.commit()

async def all_users(db):
    async with db.execute("SELECT * FROM users ORDER BY created_at") as c:
        return await c.fetchall()


# ── Rounds ────────────────────────────────────────────────────────────────────

async def get_open_round(db):
    async with db.execute("SELECT * FROM rounds WHERE status = 'open' ORDER BY id DESC LIMIT 1") as c:
        return await c.fetchone()

async def get_round(db, round_id):
    async with db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)) as c:
        return await c.fetchone()

async def create_round(db, draw_date=None):
    async with db.execute("INSERT INTO rounds (status, draw_date) VALUES ('open', ?)", (draw_date,)) as c:
        await db.commit()
        return c.lastrowid

async def close_round(db, round_id):
    await db.execute("UPDATE rounds SET status='closed', closed_at=datetime('now') WHERE id=?", (round_id,))
    await db.commit()

async def set_round_winner(db, round_id, winner_id, ticket_ref):
    await db.execute(
        "UPDATE rounds SET status='drawn', winner_id=?, ticket_ref=?, drawn_at=datetime('now') WHERE id=?",
        (winner_id, ticket_ref, round_id))
    await db.commit()

async def recent_rounds(db, limit=10):
    async with db.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT ?", (limit,)) as c:
        return await c.fetchall()

async def all_rounds_with_participation(db, user_id, limit=20):
    """Return all rounds joined with user participation data."""
    async with db.execute(
        """SELECT r.*,
             p.amount as my_stake, p.shares as my_shares, p.prize as my_prize,
             (SELECT COUNT(*) FROM participations WHERE round_id=r.id) as participants_count
           FROM rounds r
           LEFT JOIN participations p ON p.round_id=r.id AND p.user_id=?
           ORDER BY r.id DESC LIMIT ?""",
        (user_id, limit)
    ) as c:
        return await c.fetchall()


# ── Participations ────────────────────────────────────────────────────────────

async def get_participation(db, round_id, user_id):
    async with db.execute("SELECT * FROM participations WHERE round_id=? AND user_id=?", (round_id, user_id)) as c:
        return await c.fetchone()

async def upsert_participation(db, round_id, user_id, additional):
    existing = await get_participation(db, round_id, user_id)
    if existing:
        await db.execute("UPDATE participations SET amount=amount+? WHERE round_id=? AND user_id=?",
                         (additional, round_id, user_id))
    else:
        await db.execute("INSERT INTO participations (round_id, user_id, amount) VALUES (?,?,?)",
                         (round_id, user_id, additional))
    await db.execute("UPDATE rounds SET pool=pool+? WHERE id=?", (additional, round_id))
    await db.commit()

async def round_participations(db, round_id):
    async with db.execute(
        """SELECT p.*, u.full_name, u.username
           FROM participations p JOIN users u ON u.telegram_id = p.user_id
           WHERE p.round_id = ? ORDER BY p.amount DESC""", (round_id,)
    ) as c:
        return await c.fetchall()

async def user_participations(db, user_id, limit=10):
    async with db.execute(
        """SELECT p.*, r.status, r.pool, r.winner_id, r.drawn_at
           FROM participations p JOIN rounds r ON r.id = p.round_id
           WHERE p.user_id = ? ORDER BY p.round_id DESC LIMIT ?""", (user_id, limit)
    ) as c:
        return await c.fetchall()


# ── Transactions ──────────────────────────────────────────────────────────────

async def add_transaction(db, user_id, tx_type, amount, note=None):
    await db.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                     (user_id, tx_type, amount, note))
    await db.commit()

async def user_transactions(db, user_id, limit=15):
    async with db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                          (user_id, limit)) as c:
        return await c.fetchall()


# ── Deposit requests ──────────────────────────────────────────────────────────

async def create_deposit_request(db, user_id, amount):
    async with db.execute("INSERT INTO deposit_requests (user_id, amount) VALUES (?,?)", (user_id, amount)) as c:
        await db.commit()
        return c.lastrowid

async def get_deposit_request(db, req_id):
    async with db.execute("SELECT * FROM deposit_requests WHERE id=?", (req_id,)) as c:
        return await c.fetchone()

async def resolve_deposit(db, req_id, status, note=None):
    await db.execute(
        "UPDATE deposit_requests SET status=?, trustee_note=?, resolved_at=datetime('now') WHERE id=?",
        (status, note, req_id))
    await db.commit()

async def pending_deposits(db):
    async with db.execute(
        """SELECT dr.*, u.full_name, u.username
           FROM deposit_requests dr JOIN users u ON u.telegram_id = dr.user_id
           WHERE dr.status='pending' ORDER BY dr.created_at"""
    ) as c:
        return await c.fetchall()
