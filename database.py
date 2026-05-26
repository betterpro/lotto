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
            "SELECT * FROM users WHERE group_id = ? ORDER BY created_at", (group_id,)
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
