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


def distribute_value_shares(total_value: float, parts: list[dict], pool: float) -> dict[int, float]:
    """Split a dollar *total_value* across participations proportionally by stake.

    Unlike distribute_integer_shares (whole units to the biggest holders), this
    gives every participant their exact percentage — a 10% holder gets 10% of
    the value — so free-ticket winnings track each member's pool share.
    """
    if total_value <= 0 or not parts or pool <= 0:
        return {}
    return {p["user_id"]: round((p["amount"] / pool) * total_value, 2) for p in parts}


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

    # Value is shared by every participant in proportion to their stake (a 10%
    # holder gets 10% of the free-ticket value). The whole-ticket count is still
    # distributed as integers so the trustee buys the right number of tickets.
    src_type = source.get("lottery_type") or lottery_type
    src_seq = source.get("group_seq") or source["id"]
    total_value = free_ticket_cash_value(src_type, remaining)
    value_alloc = distribute_value_shares(total_value, parts, pool)
    count_alloc = distribute_integer_shares(remaining, parts, pool)

    applied_value = 0.0
    for p in parts:
        user_id = p["user_id"]
        value = value_alloc.get(user_id, 0.0)
        cnt = count_alloc.get(user_id, 0)
        if value <= 0 and cnt <= 0:
            continue
        # Activity log: free stake realized for this member (not cash — no balance change).
        if value > 0:
            await db.execute(
                "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
                (user_id, "free_win", round(value, 2), f"Free tickets — Round #{src_seq}", group_id),
            )
        cur = await db.execute(
            "SELECT * FROM participations WHERE round_id = ? AND user_id = ?",
            (round_id, user_id),
        )
        existing = await cur.fetchone()
        if existing:
            new_shares = (existing["shares"] or 0) + cnt
            new_free = (existing.get("free_ticket_shares") or 0) + cnt
            new_amount = round((existing["amount"] or 0) + value, 2)
            new_value = round((existing.get("free_ticket_value") or 0) + value, 2)
            await db.execute(
                """UPDATE participations
                   SET shares = ?, free_ticket_shares = ?, amount = ?, free_ticket_value = ?
                   WHERE round_id = ? AND user_id = ?""",
                (new_shares, new_free, new_amount, new_value, round_id, user_id),
            )
        else:
            await db.execute(
                """INSERT INTO participations
                   (round_id, user_id, amount, shares, free_ticket_shares, free_ticket_value)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (round_id, user_id, round(value, 2), cnt, cnt, round(value, 2)),
            )
        applied_value += value

    if applied_value > 0:
        await db.execute(
            "UPDATE rounds SET pool = pool + ? WHERE id = ?",
            (round(applied_value, 2), round_id),
        )
    # All pending free tickets are distributed in one pass.
    await db.execute(
        "UPDATE rounds SET free_tickets_consumed = free_tickets_won WHERE id = ?",
        (source["id"],),
    )
    return remaining
