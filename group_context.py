"""Group / trustee context helpers for multi-tenant lottery pools."""
import re
import secrets

import config


# Join codes use an unambiguous alphabet (no 0/O/1/I/L) so they are easy to
# read aloud and type. Codes are stored uppercase and matched case-insensitively.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_join_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def normalize_join_code(code: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def parse_invite_slug(start_param: str | None) -> str | None:
    if not start_param:
        return None
    sp = start_param.strip()
    if sp.startswith("join_"):
        return sp[5:].lower().strip() or None
    if sp.startswith("g_"):
        return sp[2:].lower().strip() or None
    return None


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return (s[:48] if s else "group")


async def get_group(db, group_id: int | None):
    if not group_id:
        return None
    cur = await db.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
    return await cur.fetchone()


async def get_group_by_slug(db, slug: str):
    cur = await db.execute("SELECT * FROM groups WHERE slug = ?", (slug.lower(),))
    return await cur.fetchone()


async def get_group_by_join_code(db, code: str):
    code = normalize_join_code(code)
    if not code:
        return None
    cur = await db.execute("SELECT * FROM groups WHERE join_code = ?", (code,))
    return await cur.fetchone()


async def ensure_join_code(db, group: dict) -> str:
    """Return the group's join code, allocating a unique one on first use."""
    if group.get("join_code"):
        return group["join_code"]
    for _ in range(12):
        code = generate_join_code()
        cur = await db.execute("SELECT 1 FROM groups WHERE join_code = ?", (code,))
        if await cur.fetchone():
            continue
        await db.execute("UPDATE groups SET join_code = ? WHERE id = ?", (code, group["id"]))
        await db.commit()
        return code
    raise RuntimeError("Could not allocate a unique join code")


async def get_trustee_user(db, trustee_user_id: int):
    cur = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (trustee_user_id,))
    return await cur.fetchone()


def trustee_public(trustee_row) -> dict | None:
    if not trustee_row:
        return None
    return {
        "telegram_id": trustee_row["telegram_id"],
        "full_name": trustee_row.get("full_name"),
        "username": trustee_row.get("username"),
        "photo_url": trustee_row.get("photo_url"),
    }


from free_tickets import normalize_free_ticket_mode

CARD_DEPOSIT_AMOUNTS = (25.0, 50.0, 100.0, 250.0)
VALID_PAYMENT_METHODS = ("etransfer", "card", "both")


def _normalize_payment_methods(value) -> str:
    pm = (value or "both").lower()
    return pm if pm in VALID_PAYMENT_METHODS else "both"


def group_public(group_row) -> dict | None:
    if not group_row:
        return None
    return {
        "id": group_row["id"],
        "name": group_row["name"],
        "slug": group_row["slug"],
        "status": group_row["status"],
        "payment_methods": _normalize_payment_methods(group_row.get("payment_methods")),
        "etransfer_min_amount": float(group_row.get("etransfer_min_amount") or 25),
        "etransfer_email": group_row.get("etransfer_email"),
        "free_ticket_mode": normalize_free_ticket_mode(group_row.get("free_ticket_mode")),
        "join_code": group_row.get("join_code"),
        "pricing_plan": group_row.get("pricing_plan") or "subscription",
        "stripe_connected": bool(group_row.get("stripe_account_id")),
        "stripe_charges_enabled": bool(group_row.get("stripe_charges_enabled")),
        "locked": group_row.get("status") == "locked",
        "platform_sub_status": group_row.get("platform_sub_status") or "none",
        "reminder_hours_1": int(group_row.get("reminder_hours_1") or 48),
        "reminder_hours_2": int(group_row.get("reminder_hours_2") or 24),
    }


def group_allows_payment(group_row, method: str) -> bool:
    if not group_row:
        return False
    pm = _normalize_payment_methods(group_row.get("payment_methods"))
    if method == "card":
        return pm in ("card", "both")
    if method == "etransfer":
        return pm in ("etransfer", "both")
    return False


def is_valid_card_deposit_amount(amount: float) -> bool:
    return round(float(amount), 2) in CARD_DEPOSIT_AMOUNTS


async def trustee_group_id(db, user: dict, *, active_only: bool = False) -> int | None:
    """Group id this user trustees (may differ from users.group_id)."""
    sql = "SELECT id FROM groups WHERE trustee_user_id = ?"
    if active_only:
        sql += " AND status = 'active'"
    sql += " ORDER BY id DESC LIMIT 1"
    cur = await db.execute(sql, (user["telegram_id"],))
    row = await cur.fetchone()
    return row["id"] if row else None


async def is_group_trustee(db, user: dict) -> bool:
    return await trustee_group_id(db, user) is not None


async def user_in_group(db, user_id: int, group_id: int) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    return await cur.fetchone() is not None


async def add_group_member(db, group_id: int, user_id: int, role: str = "member") -> None:
    await db.execute(
        """INSERT INTO group_members (group_id, user_id, role)
           VALUES (?, ?, ?)
           ON CONFLICT (group_id, user_id) DO NOTHING""",
        (group_id, user_id, role),
    )


async def get_user_groups(db, user_id: int) -> list[dict]:
    cur = await db.execute(
        """SELECT g.id, g.name, g.slug, g.status, g.trustee_user_id,
                  gm.role, gm.joined_at
           FROM group_members gm
           JOIN groups g ON g.id = gm.group_id
           WHERE gm.user_id = ?
           ORDER BY gm.joined_at DESC, g.name ASC""",
        (user_id,),
    )
    rows = []
    for r in await cur.fetchall():
        d = dict(r)
        d["is_trustee"] = d["trustee_user_id"] == user_id
        rows.append(d)
    return rows


def member_group_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "status": row["status"],
        "role": row.get("role"),
        "is_trustee": bool(row.get("is_trustee")),
    }


async def ensure_active_group_id(db, user: dict) -> int | None:
    """Return valid active group id; sync users.group_id when needed."""
    uid = user["telegram_id"]
    memberships = await get_user_groups(db, uid)
    if not memberships:
        return None
    gid = user.get("group_id")
    if gid and any(m["id"] == gid for m in memberships):
        return gid
    gid = memberships[0]["id"]
    await db.execute("UPDATE users SET group_id = ? WHERE telegram_id = ?", (gid, uid))
    await db.commit()
    return gid


async def join_group_by_slug(db, telegram_id: int, slug: str) -> tuple[str | None, dict | None]:
    """Add membership; set active group if user has none. Returns (error, group_row)."""
    group = await get_group_by_slug(db, slug)
    if not group:
        return "Invalid invite link", None
    if group["status"] != "active":
        return "This group is not accepting members", None
    role = "trustee" if group["trustee_user_id"] == telegram_id else "member"
    await add_group_member(db, group["id"], telegram_id, role)
    cur = await db.execute("SELECT group_id FROM users WHERE telegram_id = ?", (telegram_id,))
    row = await cur.fetchone()
    if not row or not row["group_id"]:
        await db.execute(
            "UPDATE users SET group_id = ? WHERE telegram_id = ?",
            (group["id"], telegram_id),
        )
    await db.commit()
    return None, group


async def join_group_by_code(db, telegram_id: int, code: str) -> tuple[str | None, dict | None]:
    """Add membership via a group join code. Returns (error, group_row)."""
    group = await get_group_by_join_code(db, code)
    if not group:
        return "That code didn’t match any group. Check it with your trustee.", None
    if group["status"] != "active":
        return "This group is not accepting members", None
    role = "trustee" if group["trustee_user_id"] == telegram_id else "member"
    await add_group_member(db, group["id"], telegram_id, role)
    cur = await db.execute("SELECT group_id FROM users WHERE telegram_id = ?", (telegram_id,))
    row = await cur.fetchone()
    if not row or not row["group_id"]:
        await db.execute(
            "UPDATE users SET group_id = ? WHERE telegram_id = ?",
            (group["id"], telegram_id),
        )
    await db.commit()
    return None, group


async def enrich_user_context(db, user: dict) -> dict:
    memberships = await get_user_groups(db, user["telegram_id"])
    if not memberships and user.get("group_id"):
        group = await get_group(db, user["group_id"])
        if group and group["status"] == "active":
            role = "trustee" if group["trustee_user_id"] == user["telegram_id"] else "member"
            await add_group_member(db, group["id"], user["telegram_id"], role)
            memberships = await get_user_groups(db, user["telegram_id"])
    active_gid = await ensure_active_group_id(db, user)
    group_row = await get_group(db, active_gid) if active_gid else None
    if not group_row and memberships:
        group_row = await get_group(db, memberships[0]["id"])
    trustee_row = None
    if group_row:
        trustee_row = await get_trustee_user(db, group_row["trustee_user_id"])
    is_g_trustee = await is_group_trustee(db, user)
    is_platform = bool(user.get("is_platform_admin")) or user["telegram_id"] in config.PLATFORM_ADMIN_IDS
    needs_invite = len(memberships) == 0
    onboarded = bool(user.get("agreement_accepted_at"))
    return {
        "group": group_public(group_row),
        "groups": [member_group_public(m) for m in memberships],
        "active_group_id": active_gid,
        "trustee": trustee_public(trustee_row),
        "is_group_trustee": is_g_trustee,
        "is_platform_admin": is_platform,
        "needs_invite": needs_invite,
        "onboarded": onboarded,
    }
