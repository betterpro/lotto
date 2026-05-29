"""Free-ticket prize handling for group lottery pools."""
from lottery_types import lottery_share_price

VALID_FREE_TICKET_MODES = ("next_round", "cash_credit")
DEFAULT_FREE_TICKET_MODE = "next_round"


def normalize_free_ticket_mode(value) -> str:
    mode = (value or DEFAULT_FREE_TICKET_MODE).lower()
    return mode if mode in VALID_FREE_TICKET_MODES else DEFAULT_FREE_TICKET_MODE


def distribute_integer_shares(total: int, parts: list[dict], pool: float) -> dict[int, int]:
    """Split *total* whole shares across participations proportionally by amount."""
    if total <= 0 or not parts or pool <= 0:
        return {}

    raw = [(p["user_id"], (p["amount"] / pool) * total) for p in parts]
    out = {uid: int(v) for uid, v in raw}
    remainder = total - sum(out.values())
    if remainder <= 0:
        return out

    fracs = sorted(
        ((uid, frac - int(frac)) for uid, frac in raw),
        key=lambda item: (-item[1], item[0]),
    )
    for i in range(remainder):
        out[fracs[i % len(fracs)][0]] += 1
    return out


def free_ticket_cash_value(lottery_type: str | None, free_tickets: int) -> float:
    if free_tickets <= 0:
        return 0.0
    return round(free_tickets * lottery_share_price(lottery_type), 2)


async def pending_free_ticket_source(db, group_id: int, lottery_type: str) -> dict | None:
    """Most recent drawn round with unused free tickets for this game type."""
    cur = await db.execute(
        """SELECT * FROM rounds
           WHERE group_id = ? AND lottery_type = ? AND status = 'drawn'
             AND free_tickets_won > free_tickets_consumed
           ORDER BY id DESC LIMIT 1""",
        (group_id, lottery_type),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def apply_pending_free_tickets(
    db,
    *,
    round_id: int,
    group_id: int,
    lottery_type: str,
    price_per_share: float,
) -> int:
    """
    Enroll source-round participants into *round_id* using pending free tickets.
    Returns number of free-ticket shares applied.
    """
    source = await pending_free_ticket_source(db, group_id, lottery_type)
    if not source:
        return 0

    remaining = int(source["free_tickets_won"] or 0) - int(source["free_tickets_consumed"] or 0)
    if remaining <= 0:
        return 0

    cur = await db.execute(
        "SELECT * FROM participations WHERE round_id = ? ORDER BY amount DESC",
        (source["id"],),
    )
    parts = [dict(p) for p in await cur.fetchall()]
    pool = source.get("pool") or sum(p["amount"] for p in parts)
    if not parts or pool <= 0:
        return 0

    allocation = distribute_integer_shares(remaining, parts, pool)
    applied = 0

    for user_id, shares in allocation.items():
        if shares <= 0:
            continue
        imputed_amount = round(shares * price_per_share, 2)
        cur = await db.execute(
            "SELECT * FROM participations WHERE round_id = ? AND user_id = ?",
            (round_id, user_id),
        )
        existing = await cur.fetchone()
        if existing:
            new_shares = (existing["shares"] or 0) + shares
            new_free = (existing.get("free_ticket_shares") or 0) + shares
            new_amount = (existing["amount"] or 0) + imputed_amount
            await db.execute(
                """UPDATE participations
                   SET shares = ?, free_ticket_shares = ?, amount = ?
                   WHERE round_id = ? AND user_id = ?""",
                (new_shares, new_free, new_amount, round_id, user_id),
            )
        else:
            await db.execute(
                """INSERT INTO participations
                   (round_id, user_id, amount, shares, free_ticket_shares)
                   VALUES (?, ?, ?, ?, ?)""",
                (round_id, user_id, imputed_amount, shares, shares),
            )
        applied += shares

    if applied > 0:
        imputed_pool = round(applied * price_per_share, 2)
        await db.execute(
            "UPDATE rounds SET pool = pool + ? WHERE id = ?",
            (imputed_pool, round_id),
        )
        await db.execute(
            "UPDATE rounds SET free_tickets_consumed = free_tickets_consumed + ? WHERE id = ?",
            (applied, source["id"]),
        )

    return applied
