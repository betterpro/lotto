"""Group / trustee context helpers for multi-tenant lottery pools."""
import re

import config


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


def group_public(group_row) -> dict | None:
    if not group_row:
        return None
    return {
        "id": group_row["id"],
        "name": group_row["name"],
        "slug": group_row["slug"],
        "status": group_row["status"],
    }


async def is_group_trustee(db, user: dict) -> bool:
    gid = user.get("group_id")
    if not gid:
        cur = await db.execute(
            "SELECT id FROM groups WHERE trustee_user_id = ? AND status = 'active' LIMIT 1",
            (user["telegram_id"],),
        )
        row = await cur.fetchone()
        return row is not None
    group = await get_group(db, gid)
    return bool(group and group["trustee_user_id"] == user["telegram_id"])


async def trustee_group_id(db, user: dict) -> int | None:
    """Group id this user trustees (may differ from users.group_id for trustees)."""
    cur = await db.execute(
        "SELECT id FROM groups WHERE trustee_user_id = ? AND status = 'active' LIMIT 1",
        (user["telegram_id"],),
    )
    row = await cur.fetchone()
    return row["id"] if row else None


async def enrich_user_context(db, user: dict) -> dict:
    group_row = await get_group(db, user.get("group_id"))
    trustee_row = None
    if group_row:
        trustee_row = await get_trustee_user(db, group_row["trustee_user_id"])
    is_g_trustee = await is_group_trustee(db, user)
    is_platform = bool(user.get("is_platform_admin")) or user["telegram_id"] in config.PLATFORM_ADMIN_IDS
    needs_invite = user.get("group_id") is None
    onboarded = bool(user.get("agreement_accepted_at"))
    return {
        "group": group_public(group_row),
        "trustee": trustee_public(trustee_row),
        "is_group_trustee": is_g_trustee,
        "is_platform_admin": is_platform,
        "needs_invite": needs_invite,
        "onboarded": onboarded,
    }
