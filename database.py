"""
Async PostgreSQL layer via asyncpg with an aiosqlite-compatible interface.

Drop-in replacement for the old aiosqlite layer: same get_db() signature,
same helper functions, same ? placeholders and row dict semantics.
"""
import re
from decimal import Decimal

import asyncpg

from config import DATABASE_URL

# ── Pool singleton ────────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None

async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


# ── Row dict helper ───────────────────────────────────────────────────────────

def _to_dict(row) -> dict:
    """asyncpg Record → plain dict; Decimal → float for monetary columns."""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
    return d


# ── Cursor shim ───────────────────────────────────────────────────────────────

class _Cursor:
    __slots__ = ("_rows", "lastrowid")

    def __init__(self, rows, lastrowid=None):
        self._rows = [_to_dict(r) for r in rows] if rows else []
        self.lastrowid = lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass


class _ExecuteContext:
    """Supports both `await db.execute(...)` and `async with db.execute(...) as c:`."""

    def __init__(self, coro):
        self._coro = coro

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self):
        self._cursor = await self._coro
        return self._cursor

    async def __aexit__(self, *_):
        pass


# ── SQL adapter ───────────────────────────────────────────────────────────────

_NOW = "to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"


def _adapt(sql: str, params: tuple) -> tuple[str, tuple]:
    """Translate SQLite-flavoured SQL → PostgreSQL."""
    # datetime('now') → TEXT timestamp matching SQLite's output format
    sql = re.sub(r"datetime\('now'\)", _NOW, sql, flags=re.IGNORECASE)
    # INSERT OR IGNORE INTO → INSERT INTO … ON CONFLICT DO NOTHING
    if re.search(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', sql, re.IGNORECASE):
        sql = re.sub(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT INTO', sql, flags=re.IGNORECASE)
        if 'RETURNING' in sql.upper():
            sql = re.sub(r'\bRETURNING\b', 'ON CONFLICT DO NOTHING RETURNING',
                         sql, count=1, flags=re.IGNORECASE)
        else:
            sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    # ? → $1, $2, …
    if '?' in sql:
        idx = 0
        def _repl(_m):
            nonlocal idx
            idx += 1
            return f'${idx}'
        sql = re.sub(r'\?', _repl, sql)
    return sql, params


# ── DB wrapper ────────────────────────────────────────────────────────────────

class _DB:
    """Wraps an asyncpg connection with an aiosqlite-compatible interface."""

    def __init__(self, conn: asyncpg.Connection):
        self._conn = conn

    # aiosqlite sets row_factory; ignore it
    @property
    def row_factory(self): return None
    @row_factory.setter
    def row_factory(self, _): pass

    def execute(self, sql: str, params: tuple = ()) -> _ExecuteContext:
        return _ExecuteContext(self._execute(sql, params))

    async def _execute(self, sql: str, params: tuple = ()) -> _Cursor:
        pg_sql, pg_params = _adapt(sql, params)
        upper = sql.strip().upper()
        if upper.startswith('SELECT') or upper.startswith('WITH'):
            rows = await self._conn.fetch(pg_sql, *pg_params)
            return _Cursor(rows)
        elif 'RETURNING' in upper:
            rows = await self._conn.fetch(pg_sql, *pg_params)
            lastrowid = rows[0][0] if rows else None
            return _Cursor(rows, lastrowid)
        else:
            await self._conn.execute(pg_sql, *pg_params)
            return _Cursor([])

    async def executescript(self, sql: str):
        await self._conn.execute(sql)

    async def commit(self):
        pass  # asyncpg auto-commits each statement outside a transaction block

    async def close(self):
        pool = await _get_pool()
        await pool.release(self._conn)


async def get_db() -> _DB:
    pool = await _get_pool()
    conn = await pool.acquire()
    return _DB(conn)


# Idempotent patches (keep in sync with migrations/*.sql)
_SCHEMA_STATEMENTS = [
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS payment_methods TEXT NOT NULL DEFAULT 'both'",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS etransfer_min_amount FLOAT8 NOT NULL DEFAULT 25",
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS free_ticket_mode TEXT NOT NULL DEFAULT 'next_round'",
    "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS free_tickets_won INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS free_tickets_consumed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS round_tickets TEXT",
    "ALTER TABLE participations ADD COLUMN IF NOT EXISTS free_ticket_shares INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE participations ADD COLUMN IF NOT EXISTS free_tickets_awarded INTEGER NOT NULL DEFAULT 0",
    "UPDATE groups SET free_ticket_mode = 'next_round' WHERE free_ticket_mode IS NULL",
    "UPDATE rounds SET free_tickets_won = 0 WHERE free_tickets_won IS NULL",
    "UPDATE rounds SET free_tickets_consumed = 0 WHERE free_tickets_consumed IS NULL",
    "UPDATE participations SET free_ticket_shares = 0 WHERE free_ticket_shares IS NULL",
    "UPDATE participations SET free_tickets_awarded = 0 WHERE free_tickets_awarded IS NULL",
    # Notification preferences + per-round reminder dedup flags
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS notif_contribution INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS notif_round_closed INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS reminder_48h_sent INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS reminder_24h_sent INTEGER NOT NULL DEFAULT 0",
    # Per-group round numbering (display "#1, #2, …" within each group)
    "ALTER TABLE rounds ADD COLUMN IF NOT EXISTS group_seq INTEGER",
    """UPDATE rounds r SET group_seq = n.rn
         FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY group_id ORDER BY id) AS rn
               FROM rounds) n
        WHERE r.id = n.id AND r.group_seq IS NULL""",
    # Web auth: email + password and OAuth (Google now, Apple later). See migrations/011.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_email TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS apple_sub TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_auth_email ON users (lower(auth_email)) WHERE auth_email IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users (google_sub) WHERE google_sub IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_apple_sub ON users (apple_sub) WHERE apple_sub IS NOT NULL",
    "CREATE SEQUENCE IF NOT EXISTS web_user_id_seq START 1",
    # Group join codes: trustee shares a short code, members type it to join.
    "ALTER TABLE groups ADD COLUMN IF NOT EXISTS join_code TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_join_code ON groups (join_code) WHERE join_code IS NOT NULL",
]

_schema_ready = False


async def ensure_schema() -> None:
    """Apply missing columns so admin settings (e.g. free_ticket_mode) do not 500."""
    global _schema_ready
    if _schema_ready:
        return
    db = await get_db()
    try:
        for sql in _SCHEMA_STATEMENTS:
            await db.execute(sql)
        _schema_ready = True
    finally:
        await db.close()


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user(db, telegram_id):
    async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as c:
        return await c.fetchone()

async def create_user(db, telegram_id, username, full_name, invited_by=None, is_trustee=0,
                      group_id=None, is_platform_admin=0):
    await db.execute(
        """INSERT OR IGNORE INTO users
           (telegram_id, username, full_name, invited_by, is_trustee, group_id, is_platform_admin)
           VALUES (?,?,?,?,?,?,?)""",
        (telegram_id, username, full_name, invited_by, is_trustee, group_id, is_platform_admin))
    await db.commit()


# ── Web (non-Telegram) accounts ────────────────────────────────────────────────

async def get_user_by_auth_email(db, email):
    async with db.execute(
        "SELECT * FROM users WHERE lower(auth_email) = lower(?)", (email,)
    ) as c:
        return await c.fetchone()


async def get_user_by_google_sub(db, sub):
    async with db.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)) as c:
        return await c.fetchone()


async def create_web_user(db, full_name, *, auth_email=None, password_hash=None,
                          google_sub=None, apple_sub=None, auth_provider="email",
                          photo_url=None, group_id=None):
    """Create a web-only account with a synthetic negative id and seed its settings.

    Returns the full user row dict.
    """
    async with db.execute(
        """INSERT INTO users
             (telegram_id, full_name, auth_email, password_hash, google_sub, apple_sub,
              auth_provider, photo_url, group_id)
           VALUES (-nextval('web_user_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?)
           RETURNING telegram_id""",
        (full_name, auth_email, password_hash, google_sub, apple_sub,
         auth_provider, photo_url, group_id),
    ) as c:
        uid = c.lastrowid
    await db.execute(
        "INSERT INTO user_settings (user_id) VALUES (?) ON CONFLICT (user_id) DO NOTHING",
        (uid,),
    )
    await db.commit()
    return await get_user(db, uid)


# Tables whose user-referencing column must follow an account when it is merged
# into another account. (table, column). user_settings is keyed 1:1 and handled
# specially; participations has a UNIQUE(round_id, user_id) we must respect.
_USER_FK_REPOINTS = [
    ("groups", "trustee_user_id"),
    ("users", "invited_by"),
    ("trustee_applications", "applicant_user_id"),
    ("trustee_applications", "reviewed_by"),
    ("rounds", "winner_id"),
    ("transactions", "user_id"),
    ("deposit_requests", "user_id"),
    ("stripe_subscriptions", "user_id"),
]


async def merge_users(db, from_id: int, into_id: int) -> None:
    """Move everything owned by `from_id` onto `into_id`, then delete `from_id`.

    Runs in a single Postgres transaction so a failure leaves no half-merged
    state (db.commit() is a no-op here; we drive the real transaction directly).
    `into_id` is the surviving account.
    """
    if from_id == into_id:
        return
    conn = db._conn
    async with conn.transaction():
        # Fold credit balances onto the survivor.
        await conn.execute(
            "UPDATE users SET credit = credit + "
            "(SELECT credit FROM users WHERE telegram_id = $1) WHERE telegram_id = $2",
            from_id, into_id,
        )
        # group_members: keep the survivor's role on overlap, otherwise re-point.
        await conn.execute(
            "DELETE FROM group_members gm WHERE gm.user_id = $1 AND EXISTS "
            "(SELECT 1 FROM group_members o WHERE o.group_id = gm.group_id AND o.user_id = $2)",
            from_id, into_id,
        )
        await conn.execute(
            "UPDATE group_members SET user_id = $2 WHERE user_id = $1", from_id, into_id,
        )
        # participations: UNIQUE(round_id, user_id) — drop the loser's row where
        # the survivor already participates in that round, otherwise re-point.
        await conn.execute(
            "DELETE FROM participations p WHERE p.user_id = $1 AND EXISTS "
            "(SELECT 1 FROM participations o WHERE o.round_id = p.round_id AND o.user_id = $2)",
            from_id, into_id,
        )
        await conn.execute(
            "UPDATE participations SET user_id = $2 WHERE user_id = $1", from_id, into_id,
        )
        # Simple re-points for the remaining FK columns.
        for table, col in _USER_FK_REPOINTS:
            await conn.execute(
                f"UPDATE {table} SET {col} = $2 WHERE {col} = $1", from_id, into_id,
            )
        # Carry over a group assignment / profile fields only if the survivor lacks one.
        await conn.execute(
            "UPDATE users SET group_id = COALESCE(group_id, "
            "(SELECT group_id FROM users WHERE telegram_id = $1)) WHERE telegram_id = $2",
            from_id, into_id,
        )
        await conn.execute("DELETE FROM user_settings WHERE user_id = $1", from_id)
        await conn.execute("DELETE FROM users WHERE telegram_id = $1", from_id)


# ── Groups ────────────────────────────────────────────────────────────────────

async def get_group(db, group_id):
    async with db.execute("SELECT * FROM groups WHERE id = ?", (group_id,)) as c:
        return await c.fetchone()

async def get_group_by_slug(db, slug):
    async with db.execute("SELECT * FROM groups WHERE slug = ?", (slug,)) as c:
        return await c.fetchone()

async def get_group_for_trustee(db, trustee_user_id):
    async with db.execute(
        "SELECT * FROM groups WHERE trustee_user_id = ? AND status = 'active' LIMIT 1",
        (trustee_user_id,),
    ) as c:
        return await c.fetchone()

async def get_trustee_user(db, trustee_user_id):
    async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (trustee_user_id,)) as c:
        return await c.fetchone()

async def update_credit(db, telegram_id, delta):
    await db.execute("UPDATE users SET credit = credit + ? WHERE telegram_id = ?", (delta, telegram_id))
    await db.commit()

async def all_users(db, group_id=None):
    if group_id is not None:
        async with db.execute(
            """SELECT u.* FROM users u
               JOIN group_members gm ON gm.user_id = u.telegram_id
               WHERE gm.group_id = ?
               ORDER BY gm.joined_at, u.created_at""",
            (group_id,),
        ) as c:
            return await c.fetchall()
    async with db.execute("SELECT * FROM users ORDER BY created_at") as c:
        return await c.fetchall()


# ── Rounds ────────────────────────────────────────────────────────────────────

async def get_open_round(db, group_id=None):
    if group_id is not None:
        async with db.execute(
            "SELECT * FROM rounds WHERE status = 'open' AND group_id = ? ORDER BY id DESC LIMIT 1",
            (group_id,),
        ) as c:
            return await c.fetchone()
    async with db.execute("SELECT * FROM rounds WHERE status = 'open' ORDER BY id DESC LIMIT 1") as c:
        return await c.fetchone()

async def get_round(db, round_id):
    async with db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)) as c:
        return await c.fetchone()

async def create_round(db, draw_date=None, group_id=None):
    async with db.execute(
        "INSERT INTO rounds (status, draw_date, group_id) VALUES ('open', ?, ?) RETURNING id",
        (draw_date, group_id),
    ) as c:
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

async def recent_rounds(db, limit=10, group_id=None):
    if group_id is not None:
        async with db.execute(
            "SELECT * FROM rounds WHERE group_id = ? ORDER BY id DESC LIMIT ?",
            (group_id, limit),
        ) as c:
            return await c.fetchall()
    async with db.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT ?", (limit,)) as c:
        return await c.fetchall()

async def all_rounds_with_participation(db, user_id, limit=20, group_id=None):
    if group_id is not None:
        async with db.execute(
            """SELECT r.*,
                 p.amount as my_stake, p.shares as my_shares, p.prize as my_prize,
                 (SELECT COUNT(*) FROM participations WHERE round_id=r.id) as participants_count
               FROM rounds r
               LEFT JOIN participations p ON p.round_id=r.id AND p.user_id=?
               WHERE r.group_id = ?
               ORDER BY r.id DESC LIMIT ?""",
            (user_id, group_id, limit),
        ) as c:
            return await c.fetchall()
    async with db.execute(
        """SELECT r.*,
             p.amount as my_stake, p.shares as my_shares, p.prize as my_prize,
             (SELECT COUNT(*) FROM participations WHERE round_id=r.id) as participants_count
           FROM rounds r
           LEFT JOIN participations p ON p.round_id=r.id AND p.user_id=?
           ORDER BY r.id DESC LIMIT ?""",
        (user_id, limit),
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

async def add_transaction(db, user_id, tx_type, amount, note=None, group_id=None):
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
        (user_id, tx_type, amount, note, group_id),
    )
    await db.commit()

async def user_transactions(db, user_id, limit=15):
    async with db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                          (user_id, limit)) as c:
        return await c.fetchall()


# ── Deposit requests ──────────────────────────────────────────────────────────

async def create_deposit_request(db, user_id, amount, group_id=None):
    async with db.execute(
        "INSERT INTO deposit_requests (user_id, amount, group_id) VALUES (?,?,?) RETURNING id",
        (user_id, amount, group_id),
    ) as c:
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

async def pending_deposits(db, group_id=None):
    if group_id is not None:
        async with db.execute(
            """SELECT dr.*, u.full_name, u.username
               FROM deposit_requests dr JOIN users u ON u.telegram_id = dr.user_id
               WHERE dr.status='pending' AND dr.group_id = ? ORDER BY dr.created_at""",
            (group_id,),
        ) as c:
            return await c.fetchall()
    async with db.execute(
        """SELECT dr.*, u.full_name, u.username
           FROM deposit_requests dr JOIN users u ON u.telegram_id = dr.user_id
           WHERE dr.status='pending' ORDER BY dr.created_at"""
    ) as c:
        return await c.fetchall()
