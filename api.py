"""
FastAPI application — serves the REST API, the React Mini App static files,
the Telegram bot webhook, and Stripe payment endpoints.
"""

import asyncio
import base64
import email as _email_lib
import hashlib
import hmac
import html
import imaplib
import json
import logging
import os
import random
import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr
from urllib.parse import parse_qsl

import stripe
from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException, Request
import httpx
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application

import config
from agreements import (
    build_master_agreement,
    build_round_agreement,
    build_trustee_from_user,
    lottery_label,
)
from lottery_types import (
    LOTTERY_PREFERENCE_PRICES,
    build_scan_prompt,
    count_tickets,
    format_ticket_numbers_message,
    group_rows_into_tickets,
    lottery_share_price,
    match_lines,
    merge_round_ticket_rows,
    normalize_ticket_rows,
    parse_round_tickets,
    parse_ticket_numbers,
    rows_per_ticket,
    supports_auto_results,
    valid_lottery_type,
    validate_ticket_rows,
)
from lottery_draws import (
    draw_has_occurred,
    fetch_draw_results,
    fetch_estimated_jackpot,
    hours_until_draw,
    next_draw_date,
    suggest_new_round,
)
from notif_templates import NOTIF_TEMPLATES, describe_vars, render_template
from free_tickets import (
    apply_pending_free_tickets,
    distribute_integer_shares,
    free_ticket_cash_value,
    normalize_free_ticket_mode,
)
from group_context import (
    CARD_DEPOSIT_AMOUNTS,
    VALID_PAYMENT_METHODS,
    add_group_member,
    enrich_user_context,
    ensure_active_group_id,
    ensure_join_code,
    generate_join_code,
    get_group,
    get_group_by_join_code,
    get_group_by_slug,
    get_trustee_user,
    get_user_groups,
    group_allows_payment,
    group_public,
    join_group_by_code,
    is_valid_card_deposit_amount,
    join_group_by_slug,
    member_group_public,
    parse_invite_slug,
    slugify,
    trustee_group_id,
    trustee_public,
    user_in_group,
)
from agreement_pdf import build_agreement_pdf
from emailer import email_enabled, image_attachment, pdf_attachment, send_email
from bot import build_application
from database import (
    ensure_schema,
    get_db,
    get_user,
    get_user_by_auth_user_id,
    merge_users,
)
from supabase_auth import ensure_app_user_from_supabase, verify_supabase_access_token
from web_auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    create_session_token,
    validate_telegram_login,
    verify_session_token,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

if config.STRIPE_SECRET_KEY:
    stripe.api_key = config.STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_until_draw(draw_date_str: str | None) -> int | None:
    if not draw_date_str:
        return None
    try:
        return (date.fromisoformat(draw_date_str) - date.today()).days
    except ValueError:
        return None


def entries_open(status: str, draw_date_str: str | None = None) -> bool:
    """Stakes accepted only while round is open and more than one day before draw."""
    if status != "open":
        return False
    days = _days_until_draw(draw_date_str)
    if days is None:
        return True
    return days > 1


def agreement_available(status: str, draw_date_str: str | None = None) -> bool:
    """Round draw agreement visible once entry window has closed."""
    if status != "open":
        return True
    days = _days_until_draw(draw_date_str)
    if days is None:
        return False
    return days <= 1


def draw_date_passed(draw_date_str: str | None) -> bool:
    """True on the draw date or after (calendar day has arrived)."""
    days = _days_until_draw(draw_date_str)
    return days is not None and days <= 0


def _parse_winning_numbers(winning_numbers) -> list | None:
    if winning_numbers is None:
        return None
    if isinstance(winning_numbers, str):
        try:
            parsed = json.loads(winning_numbers)
        except (json.JSONDecodeError, TypeError):
            return None
    else:
        parsed = winning_numbers
    return parsed if isinstance(parsed, list) and len(parsed) > 0 else None


def results_finalized(
    status: str,
    winning_numbers=None,
    drawn_at: str | None = None,
) -> bool:
    """Admin has entered official winning numbers (and prizes were applied)."""
    if status != "drawn" or not drawn_at:
        return False
    return _parse_winning_numbers(winning_numbers) is not None


def display_status(
    status: str,
    draw_date_str: str | None = None,
    *,
    my_prize: float | None = None,
    my_stake: float | None = None,
    my_free_tickets: int | None = None,
    winning_numbers=None,
    drawn_at: str | None = None,
) -> str:
    """
    User-facing round phase (labels in StatusPill):
      RALLY    — open for entries
      LOCKED   — closed, waiting for draw (before draw day)
      REVEALED — draw day passed or results pending (no win/loss yet)
      WON/LOST — only after admin imports winning numbers and prize
    """
    if results_finalized(status, winning_numbers, drawn_at):
        if my_stake:
            if (my_prize or 0) > 0 or (my_free_tickets or 0) > 0:
                return "WON"
            return "LOST"
        return "REVEALED"

    if status == "drawn":
        return "REVEALED"

    if status in ("uploaded", "closed"):
        if draw_date_passed(draw_date_str):
            return "REVEALED"
        return "LOCKED"

    if status != "open":
        return "REVEALED"

    if entries_open(status, draw_date_str):
        return "RALLY"
    return "LOCKED"


async def _auto_close_round_if_due(db, round_id: int) -> None:
    """Close open rounds one calendar day before draw so the trustee can buy tickets."""
    cur = await db.execute(
        "SELECT id, status, draw_date FROM rounds WHERE id=? AND status='open'",
        (round_id,),
    )
    row = await cur.fetchone()
    if not row or not row["draw_date"]:
        return
    days = _days_until_draw(row["draw_date"])
    if days is not None and days <= 1:
        await db.execute(
            "UPDATE rounds SET status='closed', closed_at=datetime('now') WHERE id=? AND status='open'",
            (round_id,),
        )
        await db.commit()
        await _notify_round_closed(db, round_id)


async def _auto_close_all_due_rounds(db) -> None:
    cur = await db.execute(
        "SELECT id FROM rounds WHERE status='open' AND draw_date IS NOT NULL"
    )
    for row in await cur.fetchall():
        await _auto_close_round_if_due(db, row["id"])


def _validate_init_data(init_data: str) -> dict | None:
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        return None
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None
    return params


def _init_start_param(params: dict) -> str | None:
    return params.get("start_param") or None


async def _assign_group_from_slug(db, telegram_id: int, slug: str) -> str | None:
    """Add group membership from invite slug. Returns error message or None on success."""
    err, _group = await join_group_by_slug(db, telegram_id, slug)
    return err


async def _sync_user_from_tg(db, tg: dict, invite_slug: str | None = None):
    """Load or create user from Telegram user dict; optional invite slug join."""
    row = await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg["id"],))
    user = await row.fetchone()
    if user is None:
        # Auto-register on first Mini App open using Telegram initData
        full_name = " ".join(filter(None, [
            tg.get("first_name", ""), tg.get("last_name", "")
        ])).strip() or tg.get("username") or f"user_{tg['id']}"
        is_platform = 1 if tg["id"] in config.PLATFORM_ADMIN_IDS else 0
        group_id = None
        invite_g = None
        if invite_slug:
            invite_g = await get_group_by_slug(db, invite_slug)
            if invite_g and invite_g["status"] == "active":
                group_id = invite_g["id"]
        await db.execute(
            """INSERT INTO users
               (telegram_id, username, full_name, is_trustee, is_platform_admin, group_id)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT (telegram_id) DO NOTHING""",
            (tg["id"], tg.get("username"), full_name, 0, is_platform, group_id),
        )
        await db.execute(
            "INSERT INTO user_settings (user_id) VALUES (?) ON CONFLICT (user_id) DO NOTHING",
            (tg["id"],),
        )
        if group_id and invite_g:
            role = "trustee" if invite_g["trustee_user_id"] == tg["id"] else "member"
            await add_group_member(db, group_id, tg["id"], role)
        await db.commit()
        row = await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg["id"],))
        user = await row.fetchone()
    elif invite_slug:
        err = await _assign_group_from_slug(db, tg["id"], invite_slug)
        if err:
            user = dict(user)
            user["_invite_error"] = err
        else:
            row = await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg["id"],))
            user = await row.fetchone()
    user = dict(user)
    if user["telegram_id"] in config.PLATFORM_ADMIN_IDS and not user.get("is_platform_admin"):
        await db.execute(
            "UPDATE users SET is_platform_admin=1 WHERE telegram_id=?", (tg["id"],)
        )
        await db.commit()
        user["is_platform_admin"] = 1
    # Sync photo_url from Telegram initData if present and changed
    photo_url = tg.get("photo_url")
    if photo_url and user.get("photo_url") != photo_url:
        await db.execute("UPDATE users SET photo_url=? WHERE telegram_id=?", (photo_url, tg["id"]))
        await db.commit()
        user["photo_url"] = photo_url
    # If still no photo stored, trigger a background fetch via Bot API (non-blocking)
    elif not user.get("photo_url") and _ptb_app:
        asyncio.ensure_future(_bg_fetch_photo(tg["id"]))
    return user


async def _get_user(init_data: str, db):
    params = _validate_init_data(init_data)
    if params is None:
        raise HTTPException(401, "Invalid initData")
    user_json = params.get("user")
    if not user_json:
        raise HTTPException(401, "No user in initData")
    tg = json.loads(user_json)
    invite_slug = parse_invite_slug(_init_start_param(params))
    return await _sync_user_from_tg(db, tg, invite_slug)


async def _get_user_by_id(db, telegram_id: int):
    row = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    user = await row.fetchone()
    if user is None:
        raise HTTPException(401, "User not found")
    return dict(user)


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def _open_app_markup() -> InlineKeyboardMarkup | None:
    if not _bot_username:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Open LottoChee 🎟", url=f"https://t.me/{_bot_username}?startapp=open")
    ]])


# Overrides keyed by (group_id, key). group_id 0 = platform default (super-admin);
# group_id>0 = per-group override (trustee). Lookup precedence: group → platform → code.
_NOTIF_OVERRIDES: dict[tuple, str] = {}


async def _load_notif_overrides(db=None):
    """Cache notification-template overrides (call at startup + on edit)."""
    own = db is None
    if own:
        db = await get_db()
    try:
        cur = await db.execute("SELECT group_id, key, text FROM notif_templates")
        rows = await cur.fetchall()
        _NOTIF_OVERRIDES.clear()
        for r in rows:
            _NOTIF_OVERRIDES[(int(r["group_id"] or 0), r["key"])] = r["text"]
    except Exception:
        pass
    finally:
        if own:
            await db.close()


def render_notif(key: str, group_id=0, **vars) -> str:
    """Render a notification: group override → platform override → code default."""
    gid = int(group_id or 0)
    tmpl = (
        _NOTIF_OVERRIDES.get((gid, key))
        or _NOTIF_OVERRIDES.get((0, key))
        or NOTIF_TEMPLATES.get(key, {}).get("default", "")
    )
    return render_template(tmpl, vars)


async def _notify(telegram_id: int, text: str):
    """Send a Telegram message with an Open App button. Silently swallows errors."""
    if _ptb_app is None:
        return
    try:
        await _ptb_app.bot.send_message(
            chat_id=telegram_id,
            text=text,
            parse_mode="HTML",
            reply_markup=_open_app_markup(),
        )
    except Exception as e:
        log.debug("Notification to %s skipped: %s", telegram_id, e)


async def _bg_fetch_photo(telegram_id: int):
    """Background task: fetch Telegram profile photo via Bot API and store as data URL."""
    if _ptb_app is None:
        return
    try:
        photos = await _ptb_app.bot.get_user_profile_photos(telegram_id, limit=1)
        if not photos.photos:
            return
        # Use the smallest available size to keep DB lean (~160×160)
        photo_size = photos.photos[0][0]
        file_obj   = await _ptb_app.bot.get_file(photo_size.file_id)
        image_bytes = bytes(await file_obj.download_as_bytearray())
        b64 = base64.b64encode(image_bytes).decode()
        data_url = f"data:image/jpeg;base64,{b64}"
        db = await get_db()
        try:
            await db.execute(
                "UPDATE users SET photo_url=? WHERE telegram_id=?", (data_url, telegram_id)
            )
            await db.commit()
        finally:
            await db.close()
        log.debug("Stored profile photo for user %s (%d bytes)", telegram_id, len(image_bytes))
    except Exception as exc:
        log.debug("Background photo fetch failed for %s: %s", telegram_id, exc)


async def _round_tickets_required(db, round_) -> int:
    """Physical tickets to upload = total shares purchased in the round."""
    cur = await db.execute(
        "SELECT COALESCE(SUM(shares), 0) AS n FROM participations WHERE round_id=?",
        (round_["id"],),
    )
    row = await cur.fetchone()
    total = int(row["n"] or 0)
    if total > 0:
        return total
    pool = float(round_.get("pool") or 0)
    pps = float(round_.get("price_per_share") or 5)
    if pool > 0 and pps > 0:
        return max(1, int(round(pool / pps)))
    return 1


async def _save_round_tickets_json(db, round_id: int, tickets: list[dict]) -> None:
    await db.execute(
        "UPDATE rounds SET round_tickets=? WHERE id=?",
        (json.dumps(tickets), round_id),
    )


async def _upload_ticket_to_storage(
    round_id: int, image_bytes: bytes, media_type: str, ticket_index: int = 0
) -> str:
    """Upload ticket image to Supabase Storage bucket 'tickets'; return public URL."""
    ext = "jpg" if "jpeg" in media_type else media_type.split("/")[-1]
    path = f"round-{round_id}-ticket-{ticket_index}.{ext}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{config.SUPABASE_URL}/storage/v1/object/tickets/{path}",
            content=image_bytes,
            headers={
                "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
                "Content-Type": media_type,
                "x-upsert": "true",
            },
        )
        resp.raise_for_status()
    return f"{config.SUPABASE_URL}/storage/v1/object/public/tickets/{path}"


async def _notify_all(db, text: str, setting_col: str | None = None, group_id: int | None = None):
    """Notify users in a group, optionally filtering by a user_settings boolean column."""
    if setting_col:
        if group_id is not None:
            cur = await db.execute(f"""
                SELECT u.telegram_id FROM users u
                JOIN group_members gm ON gm.user_id = u.telegram_id AND gm.group_id = ?
                LEFT JOIN user_settings s ON s.user_id = u.telegram_id
                WHERE COALESCE(s.{setting_col}, 1) = 1
            """, (group_id,))
        else:
            cur = await db.execute(f"""
                SELECT u.telegram_id FROM users u
                LEFT JOIN user_settings s ON s.user_id = u.telegram_id
                WHERE COALESCE(s.{setting_col}, 1) = 1
            """)
    else:
        if group_id is not None:
            cur = await db.execute(
                """SELECT u.telegram_id FROM users u
                   JOIN group_members gm ON gm.user_id = u.telegram_id
                   WHERE gm.group_id = ?""",
                (group_id,),
            )
        else:
            cur = await db.execute("SELECT telegram_id FROM users")
    for row in await cur.fetchall():
        await _notify(row["telegram_id"], text)


async def _notify_round_contribution(db, round_d: dict, contributor: dict):
    """Tell the round's other participants that a member added to the pool."""
    rid = round_d["id"]
    name = contributor.get("full_name") or contributor.get("username") or "A member"
    pool = float(round_d.get("pool") or 0)
    text = render_notif("contribution", group_id=round_d.get("group_id"),
                        name=html.escape(name), rid=rid, pool=f"{pool:.0f}")
    cur = await db.execute(
        """SELECT p.user_id FROM participations p
           LEFT JOIN user_settings s ON s.user_id = p.user_id
           WHERE p.round_id = ? AND p.user_id != ?
             AND COALESCE(s.notif_contribution, 1) = 1""",
        (rid, contributor["telegram_id"]),
    )
    for row in await cur.fetchall():
        await _notify(row["user_id"], text)


async def _notify_round_closed(db, round_id: int):
    """Tell the group's trustee a round closed so they can buy the physical ticket."""
    cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_id,))
    round_ = await cur.fetchone()
    if not round_:
        return
    round_d = dict(round_)
    gid = round_d.get("group_id")
    if gid is None:
        return
    cur = await db.execute("SELECT trustee_user_id FROM groups WHERE id=?", (gid,))
    grow = await cur.fetchone()
    if not grow or not grow["trustee_user_id"]:
        return
    trustee_id = grow["trustee_user_id"]
    cur = await db.execute(
        "SELECT COALESCE(notif_round_closed, 1) AS enabled FROM user_settings WHERE user_id=?",
        (trustee_id,),
    )
    srow = await cur.fetchone()
    if srow is not None and not srow["enabled"]:
        return
    tickets = await _round_tickets_required(db, round_d)
    pool = float(round_d.get("pool") or 0)
    draw = round_d.get("draw_date")
    draw_str = f" · draw {html.escape(str(draw))}" if draw else ""
    await _notify(
        trustee_id,
        render_notif("round_closed_trustee", group_id=round_d.get("group_id"),
                     rid=round_id, pool=f"{pool:.0f}",
                     tickets=tickets, ticket_s="" if tickets == 1 else "s", draw=draw_str),
    )


async def _remind_non_contributors(db, round_d: dict, hours: int):
    """Nudge group members who haven't joined this round yet, before entries close."""
    rid = round_d["id"]
    gid = round_d.get("group_id")
    if gid is None:
        return
    emoji = "⏰" if hours >= 48 else "⏳"
    jackpot = int(round_d.get("jackpot") or 0)
    jp = f" · <b>${jackpot:,}</b> jackpot" if jackpot else ""
    text = render_notif("round_closing", group_id=gid, emoji=emoji, rid=rid, hours=hours, jp=jp)
    cur = await db.execute(
        """SELECT u.telegram_id FROM users u
           JOIN group_members gm ON gm.user_id = u.telegram_id AND gm.group_id = ?
           LEFT JOIN user_settings s ON s.user_id = u.telegram_id
           WHERE COALESCE(s.notif_reminder, 1) = 1
             AND NOT EXISTS (
                 SELECT 1 FROM participations p
                 WHERE p.round_id = ? AND p.user_id = u.telegram_id
             )""",
        (gid, rid),
    )
    for row in await cur.fetchall():
        await _notify(row["telegram_id"], text)


async def _send_round_reminders(db):
    """Send 48h / 24h pre-close reminders once each, tracked by per-round flags."""
    cur = await db.execute(
        """SELECT r.id, r.group_id, r.draw_date, r.jackpot, r.pool, r.lottery_type,
                  COALESCE(r.reminder_48h_sent, 0) AS r1,
                  COALESCE(r.reminder_24h_sent, 0) AS r2,
                  COALESCE(g.reminder_hours_1, 48) AS h1,
                  COALESCE(g.reminder_hours_2, 24) AS h2
           FROM rounds r LEFT JOIN groups g ON g.id = r.group_id
           WHERE r.status='open' AND r.draw_date IS NOT NULL"""
    )
    for r in await cur.fetchall():
        rem = hours_until_draw(r.get("lottery_type") or "lotto_max", r["draw_date"])
        if rem is None or rem < 0:
            continue
        h1, h2 = int(r["h1"] or 0), int(r["h2"] or 0)
        # First (earlier) reminder, then the second — each fires once. Hours are
        # per-group and shown in the message.
        if h1 > 0 and rem <= h1 and not r["r1"]:
            await _remind_non_contributors(db, dict(r), h1)
            await db.execute("UPDATE rounds SET reminder_48h_sent=1 WHERE id=?", (r["id"],))
            await db.commit()
        elif h2 > 0 and rem <= h2 and not r["r2"]:
            await _remind_non_contributors(db, dict(r), h2)
            await db.execute("UPDATE rounds SET reminder_24h_sent=1 WHERE id=?", (r["id"],))
            await db.commit()


async def _auto_join_round(db, round_id: int, price_per_share: float, group_id: int | None = None):
    """Auto-enter users who opted in, have balance, and haven't hit their monthly limit."""
    from datetime import date as _date
    month_start = _date.today().replace(day=1).isoformat()

    if group_id is not None:
        cur = await db.execute("""
            SELECT u.telegram_id, u.credit, u.full_name,
                   COALESCE(s.shares_per_round, 1)        AS shares,
                   COALESCE(s.max_rounds_per_month, 4)    AS max_mo,
                   COALESCE(s.lottery_preference, 'both') AS lottery_preference,
                   s.preferred_day
            FROM users u
            JOIN user_settings s ON s.user_id = u.telegram_id
            WHERE s.auto_participate = 1
              AND u.group_id = ?
              AND EXISTS (
                SELECT 1 FROM group_members gm
                WHERE gm.user_id = u.telegram_id AND gm.group_id = ?
              )
        """, (group_id, group_id))
    else:
        cur = await db.execute("""
            SELECT u.telegram_id, u.credit, u.full_name,
                   COALESCE(s.shares_per_round, 1)        AS shares,
                   COALESCE(s.max_rounds_per_month, 4)    AS max_mo,
                   COALESCE(s.lottery_preference, 'both') AS lottery_preference,
                   s.preferred_day
            FROM users u
            JOIN user_settings s ON s.user_id = u.telegram_id
            WHERE s.auto_participate = 1
        """)
    # Determine the round's lottery type for filtering
    round_cur = await db.execute("SELECT lottery_type FROM rounds WHERE id=?", (round_id,))
    round_row = await round_cur.fetchone()
    round_lottery_type = (round_row["lottery_type"] if round_row else None) or "lotto_max"

    for u in await cur.fetchall():
        # Skip if user's lottery preference doesn't include this round's type
        pref = u["lottery_preference"]
        if pref != "both" and pref != round_lottery_type:
            continue

        # Use the share price matching user's preference, not necessarily the round's price
        shares = u["shares"]
        amount = shares * lottery_share_price(pref, default=price_per_share)

        # Monthly participation limit
        cnt_cur = await db.execute("""
            SELECT COUNT(*) AS cnt FROM participations p
            JOIN rounds r ON r.id = p.round_id
            WHERE p.user_id = ? AND r.opened_at >= ?
        """, (u["telegram_id"], month_start))
        cnt_row = await cnt_cur.fetchone()
        if (cnt_row["cnt"] or 0) >= u["max_mo"]:
            continue

        # Balance check
        if u["credit"] < amount:
            await _notify(u["telegram_id"], render_notif(
                "auto_join_skipped", group_id=group_id, rid=round_id,
                balance=f"{u['credit']:.2f}", needed=f"{amount:.2f}"))
            continue

        # Already in this round?
        dup = await db.execute(
            "SELECT id FROM participations WHERE round_id=? AND user_id=?",
            (round_id, u["telegram_id"])
        )
        if await dup.fetchone():
            continue

        await db.execute(
            "INSERT INTO participations (round_id, user_id, amount, shares) VALUES (?,?,?,?)",
            (round_id, u["telegram_id"], amount, shares)
        )
        await db.execute("UPDATE rounds SET pool=pool+? WHERE id=?", (amount, round_id))
        await db.execute("UPDATE users SET credit=credit-? WHERE telegram_id=?",
                         (amount, u["telegram_id"]))
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (u["telegram_id"], "participate", -amount, f"Auto-join Round #{round_id}")
        )
        await db.commit()
        bal = u["credit"] - amount
        await _notify(u["telegram_id"], render_notif(
            "auto_joined", group_id=group_id, rid=round_id, shares=shares,
            share_s="" if shares == 1 else "s", amount=f"{amount:.2f}", balance=f"{bal:.2f}"))


# ---------------------------------------------------------------------------
# E-transfer / IMAP helpers
# ---------------------------------------------------------------------------

def _email_text(msg) -> str:
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    parts.append(part.get_payload(decode=True).decode("utf-8", errors="ignore"))
                except Exception:
                    pass
        return " ".join(parts)
    try:
        return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _email_addr(value: str | None) -> str:
    return (parseaddr(value or "")[1] or "").strip().lower()


def _parse_etransfer_amount(text: str) -> float | None:
    patterns = [
        r"sent\s+you\s+\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        r"you\s+have\s+\$?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*\(CAD\)",
        r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*(?:CAD|waiting)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return round(float(match.group(1).replace(",", "")), 2)
            except ValueError:
                return None
    return None


def _is_interac_message(msg, text: str) -> bool:
    from_addr = _email_addr(msg.get("From"))
    return_path = _email_addr(msg.get("Return-Path"))
    subject = msg.get("Subject") or ""
    is_interac_domain = (
        from_addr.endswith("@payments.interac.ca")
        or return_path.endswith("@payments.interac.ca")
    )
    mentions_etransfer = (
        "interac e-transfer" in subject.lower()
        or "interac e-transfer" in text.lower()
        or "autodeposit" in subject.lower()
        or "autodeposit" in text.lower()
    )
    return is_interac_domain and mentions_etransfer


def _imap_find_etransfer_receipts() -> list[dict]:
    """Synchronous IMAP scan. Returns recent Interac e-transfer email receipts."""
    if not all([config.IMAP_HOST, config.IMAP_USER, config.IMAP_PASS]):
        return []
    found: list[dict] = []
    seen_ids: set[bytes] = set()
    try:
        mail = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
        mail.login(config.IMAP_USER, config.IMAP_PASS)
        mail.select("INBOX")
        for term in [
            'FROM "payments.interac.ca"',
            'SUBJECT "Interac"',
            'SUBJECT "interac"',
            'SUBJECT "e-Transfer"',
            'SUBJECT "etransfer"',
            'SUBJECT "Autodeposit"',
        ]:
            _, msg_ids = mail.search(None, term)
            if not msg_ids[0]:
                continue
            for mid in msg_ids[0].split()[-100:]:
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                _, data = mail.fetch(mid, "(RFC822)")
                if not data[0]:
                    continue
                msg = _email_lib.message_from_bytes(data[0][1])
                text = _email_text(msg)
                subject = msg.get("Subject") or ""
                searchable = f"{text} {subject}"
                if not _is_interac_message(msg, searchable):
                    continue
                ref_ids = [
                    int(m.group(1))
                    for m in re.finditer(r"LOTTO-(\d+)", searchable, re.IGNORECASE)
                ]
                found.append({
                    "message_id": (msg.get("Message-ID") or "").strip(),
                    "payment_notification": (msg.get("X-Payment-Notification") or "").strip(),
                    "sender_email": _email_addr(msg.get("Reply-To")),
                    "amount": _parse_etransfer_amount(searchable),
                    "ref_ids": ref_ids,
                })
        mail.close()
        mail.logout()
    except Exception as exc:
        log.warning("IMAP check error: %s", exc)
    return found


async def _receipt_was_used(db, receipt: dict) -> bool:
    keys = [receipt.get("message_id"), receipt.get("payment_notification")]
    keys = [key for key in keys if key]
    if not keys:
        return False
    if len(keys) == 1:
        cur = await db.execute(
            "SELECT id FROM etransfer_email_receipts WHERE message_id=? OR payment_notification=? LIMIT 1",
            (keys[0], keys[0]),
        )
    else:
        cur = await db.execute(
            "SELECT id FROM etransfer_email_receipts WHERE message_id=? OR payment_notification=? LIMIT 1",
            (keys[0], keys[1]),
        )
    return await cur.fetchone() is not None


async def _claim_receipt(db, receipt: dict, dep_id: int) -> bool:
    cur = await db.execute(
        """INSERT INTO etransfer_email_receipts
             (message_id, payment_notification, sender_email, amount, deposit_request_id)
           VALUES (?,?,?,?,?)
           ON CONFLICT DO NOTHING
           RETURNING id""",
        (
            receipt.get("message_id") or None,
            receipt.get("payment_notification") or None,
            receipt.get("sender_email") or None,
            receipt.get("amount"),
            dep_id,
        ),
    )
    return await cur.fetchone() is not None


async def _pending_deposit_by_receipt(db, receipt: dict):
    for dep_id in receipt.get("ref_ids") or []:
        cur = await db.execute(
            "SELECT * FROM deposit_requests WHERE id=? AND status='pending' AND payment_method='etransfer'",
            (dep_id,),
        )
        dep = await cur.fetchone()
        if dep:
            return dep

    sender_email = receipt.get("sender_email")
    amount = receipt.get("amount")
    if not sender_email or amount is None:
        return None

    cur = await db.execute(
        """SELECT dr.*
           FROM deposit_requests dr
           JOIN users u ON u.telegram_id=dr.user_id
           WHERE dr.status='pending'
             AND dr.payment_method='etransfer'
             AND LOWER(COALESCE(u.email, ''))=?
             AND ABS(dr.amount - ?) < 0.01
           ORDER BY dr.created_at
           LIMIT 2""",
        (sender_email, amount),
    )
    matches = await cur.fetchall()
    return matches[0] if len(matches) == 1 else None


async def _approve_etransfer_deposit(db, dep: dict, receipt: dict) -> bool:
    note = f"Auto-approved via IMAP ({receipt.get('sender_email') or 'unknown sender'})"
    cur = await db.execute(
        "UPDATE deposit_requests SET status='approved', resolved_at=datetime('now'), trustee_note=? "
        "WHERE id=? AND status='pending' RETURNING id",
        (note, dep["id"]),
    )
    if await cur.fetchone() is None:
        return False

    await db.execute(
        "UPDATE users SET credit=credit+? WHERE telegram_id=?", (dep["amount"], dep["user_id"])
    )
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (dep["user_id"], "deposit", dep["amount"], f"E-transfer deposit #{dep['id']}"),
    )
    await db.commit()
    await _notify(dep["user_id"], render_notif("etransfer_received",
                  group_id=dep.get("group_id"), amount=f"{dep['amount']:.2f}"))
    return True


async def _check_etransfer_emails(db) -> dict:
    """Check IMAP and auto-approve pending e-transfer deposits matched by ref or sender/amount."""
    receipts = await asyncio.to_thread(_imap_find_etransfer_receipts)
    approved = 0
    for receipt in receipts:
        if await _receipt_was_used(db, receipt):
            continue
        dep = await _pending_deposit_by_receipt(db, receipt)
        if not dep:
            continue
        if not await _claim_receipt(db, receipt, dep["id"]):
            continue
        if await _approve_etransfer_deposit(db, dep, receipt):
            approved += 1
    return {"checked": len(receipts), "approved": approved}


async def _auth(request: Request):
    init_data = request.headers.get("x-init-data") or request.headers.get("X-Init-Data")
    db = await get_db()
    if init_data:
        user = await _get_user(init_data, db)
        return user, db

    auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        su = await verify_supabase_access_token(token)
        if su:
            user = await get_user_by_auth_user_id(db, su["id"])
            if not user:
                user = await ensure_app_user_from_supabase(db, su=su)
            return user, db
        await db.close()
        raise HTTPException(401, "Session expired")

    session = request.cookies.get(SESSION_COOKIE)
    if session:
        telegram_id = verify_session_token(session)
        if telegram_id is not None:
            user = await _get_user_by_id(db, telegram_id)
            return user, db
        await db.close()
        raise HTTPException(401, "Session expired")
    await db.close()
    raise HTTPException(401, "Not authenticated")


async def _auth_with_query_token(request: Request):
    """Like _auth, but a signed session token in the ?t= query param takes
    precedence. Needed for file downloads opened in an external browser (e.g.
    from Telegram's webview), and so a stale cookie in the browser the link is
    opened in doesn't override the identity the link was minted for."""
    token = request.query_params.get("t")
    if token:
        uid = verify_session_token(token)
        if uid is not None:
            db = await get_db()
            user = await _get_user_by_id(db, uid)
            return user, db
        # invalid/expired token — fall back to normal cookie/header auth
    return await _auth(request)


async def _require_group_trustee(request: Request, allow_locked: bool = False):
    user, db = await _auth(request)
    gid = await trustee_group_id(db, user)
    if not gid and user.get("group_id"):
        g = await get_group(db, user["group_id"])
        if g and g["trustee_user_id"] == user["telegram_id"]:
            gid = g["id"]
    if not gid:
        await db.close()
        raise HTTPException(403, "Group trustee only")
    group = await get_group(db, gid)
    if not group or group["trustee_user_id"] != user["telegram_id"]:
        await db.close()
        raise HTTPException(403, "Group trustee only")
    if not allow_locked and group["status"] == "locked":
        await db.close()
        raise HTTPException(403, "GROUP_LOCKED: subscription cancelled — reactivate to unlock the group")
    return user, db, group


async def _require_platform_admin(request: Request):
    user, db = await _auth(request)
    if not user.get("is_platform_admin") and user["telegram_id"] not in config.PLATFORM_ADMIN_IDS:
        raise HTTPException(403, "Platform admin only")
    return user, db


# Backward-compatible alias
async def _require_trustee(request: Request):
    user, db, _group = await _require_group_trustee(request)
    return user, db


async def _get_or_create_customer(user: dict, db) -> str:
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    customer = stripe.Customer.create(
        metadata={"telegram_id": str(user["telegram_id"])},
        name=user.get("full_name") or user.get("username") or f"user_{user['telegram_id']}",
    )
    await db.execute(
        "UPDATE users SET stripe_customer_id=? WHERE telegram_id=?", (customer.id, user["telegram_id"])
    )
    await db.commit()
    return customer.id


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

_ptb_app: Application | None = None
_bot_username: str | None = None
_etransfer_task: asyncio.Task | None = None
_round_task: asyncio.Task | None = None

# How often to close due rounds and send pre-close reminders. Reminders are
# day-granular, so a half-hour cadence is plenty and stays cheap.
ROUND_MAINTENANCE_INTERVAL_SECONDS = 1800


async def _notify_round_results(db, rd, numbers, bonus, m):
    """Tell each participant whether the pool won, based on the matched lines."""
    seq = rd.get("group_seq") or rd["id"]
    nums_html = "  ".join(f"<b>{int(n)}</b>" for n in numbers)
    bonus_html = f" · bonus <b>{int(bonus)}</b>" if bonus not in (None, "") else ""
    key = "results_auto_win" if m["any_win"] else "results_auto_nowin"
    body = render_notif(key, group_id=rd.get("group_id"), seq=seq,
                        numbers=nums_html, bonus=bonus_html, best=m["best_label"])
    cur = await db.execute(
        """SELECT p.user_id FROM participations p
           LEFT JOIN user_settings s ON s.user_id = p.user_id
           WHERE p.round_id=? AND COALESCE(s.notif_results, 1) = 1""",
        (rd["id"],),
    )
    for r in await cur.fetchall():
        await _notify(r["user_id"], body)


async def _fetch_and_apply_results(db):
    """Auto-fetch official winning numbers for past draws, match the pool's lines,
    and notify participants. Does NOT distribute cash — the trustee still confirms
    the prize via the results screen (which is pre-filled with these numbers)."""
    if not config.AUTO_RESULTS_ENABLED:
        return
    cur = await db.execute(
        """SELECT * FROM rounds
           WHERE (winning_numbers IS NULL OR winning_numbers = '')
             AND results_auto_at IS NULL
             AND status IN ('closed', 'uploaded')
             AND draw_date IS NOT NULL
             AND ticket_numbers IS NOT NULL
             AND lottery_type IN ('lotto_max', '649')
           ORDER BY id DESC LIMIT 50"""
    )
    rows = await cur.fetchall()
    for row in rows:
        rd = dict(row)
        lt = rd.get("lottery_type")
        if not supports_auto_results(lt) or not draw_has_occurred(lt, rd.get("draw_date")):
            continue
        pc = await db.execute("SELECT COUNT(*) AS n FROM participations WHERE round_id=?", (rd["id"],))
        if int((await pc.fetchone())["n"] or 0) == 0:
            continue
        try:
            res = await fetch_draw_results(lt, rd["draw_date"])
        except Exception:
            res = None
        if not res or not res.get("numbers"):
            continue  # couldn't read confidently — retry next cycle / trustee enters manually
        numbers, bonus = res["numbers"], res.get("bonus")
        lines = parse_ticket_numbers(rd.get("ticket_numbers"))
        m = match_lines(lt, numbers, bonus, lines)
        await db.execute(
            "UPDATE rounds SET winning_numbers=?, bonus_number=?, results_auto_at=datetime('now') WHERE id=?",
            (json.dumps(numbers), bonus, rd["id"]),
        )
        await db.commit()
        await _notify_round_results(db, rd, numbers, bonus, m)


async def _round_maintenance_loop():
    while True:
        try:
            db = await get_db()
            try:
                await _auto_close_all_due_rounds(db)
                await _send_round_reminders(db)
                await _fetch_and_apply_results(db)
            finally:
                await db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Background round maintenance failed")
        await asyncio.sleep(ROUND_MAINTENANCE_INTERVAL_SECONDS)


async def _etransfer_poll_loop():
    while True:
        try:
            db = await get_db()
            try:
                result = await _check_etransfer_emails(db)
                if result.get("approved"):
                    log.info("Auto-approved %s e-transfer deposit(s)", result["approved"])
            finally:
                await db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Background e-transfer check failed")
        await asyncio.sleep(max(30, config.ETRANSFER_CHECK_INTERVAL_SECONDS))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ptb_app, _bot_username, _etransfer_task, _round_task
    try:
        await ensure_schema()
        log.info("Database schema verified")
    except Exception:
        log.exception("Schema bootstrap failed — run migrations in Supabase SQL Editor")
    try:
        await _load_notif_overrides()
    except Exception:
        log.exception("Notification template load failed")
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url and not config.MINI_APP_URL:
        os.environ["MINI_APP_URL"] = render_url
        config.MINI_APP_URL = render_url
    _ptb_app = build_application()
    await _ptb_app.initialize()
    await _ptb_app.start()
    try:
        bot_info = await _ptb_app.bot.get_me()
        _bot_username = bot_info.username
    except Exception:
        pass
    log.info("PTB started (webhook mode), bot=@%s", _bot_username)
    if all([config.IMAP_HOST, config.IMAP_USER, config.IMAP_PASS]):
        _etransfer_task = asyncio.create_task(_etransfer_poll_loop())
        log.info("Background e-transfer checker started")
    _round_task = asyncio.create_task(_round_maintenance_loop())
    log.info("Background round maintenance started")
    yield
    for _task in (_etransfer_task, _round_task):
        if _task:
            _task.cancel()
            try:
                await _task
            except asyncio.CancelledError:
                pass
    await _ptb_app.stop()
    await _ptb_app.shutdown()


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, _ptb_app.bot)
    await _ptb_app.process_update(update)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Web auth (Telegram Login Widget + session cookie)
# ---------------------------------------------------------------------------

def _session_cookie(token: str) -> str:
    secure = os.getenv("RENDER", "") == "true" or os.getenv("SESSION_COOKIE_SECURE", "") == "1"
    parts = [
        f"{SESSION_COOKIE}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={SESSION_MAX_AGE}",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


@app.get("/api/auth/config")
async def api_auth_config():
    return {
        "bot_username": _bot_username,
        "google_client_id": config.GOOGLE_CLIENT_ID or None,
        "apple_client_id": config.APPLE_CLIENT_ID or None,
        "supabase_url": config.SUPABASE_URL or None,
        "supabase_anon_key": config.SUPABASE_ANON_KEY or None,
    }


def _bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    return None


def _session_response(uid: int, **extra) -> Response:
    token = create_session_token(uid)
    return Response(
        content=json.dumps({"ok": True, "telegram_id": uid, **extra}),
        media_type="application/json",
        headers={"Set-Cookie": _session_cookie(token)},
    )


def _current_session_uid(request: Request) -> int | None:
    """Resolve the caller's existing session id (may be a negative web id)."""
    cookie = request.cookies.get(SESSION_COOKIE)
    return verify_session_token(cookie) if cookie else None


@app.post("/api/auth/telegram")
async def api_auth_telegram(request: Request):
    body = await request.json()
    tg = validate_telegram_login(body)
    if tg is None:
        raise HTTPException(401, "Invalid Telegram login")
    prior_uid = _current_session_uid(request)
    db = await get_db()
    try:
        user = await _sync_user_from_tg(db, tg)
        # Account linking: if the caller was signed in as a web-only account
        # (synthetic negative id), merge that account into this Telegram one.
        if prior_uid is not None and prior_uid < 0 and prior_uid != user["telegram_id"]:
            web = await get_user(db, prior_uid)
            if web:
                await _carry_over_credentials(db, web, user["telegram_id"])
                await merge_users(db, prior_uid, user["telegram_id"])
                user = await get_user(db, user["telegram_id"])
    finally:
        await db.close()
    return _session_response(user["telegram_id"])


async def _carry_over_credentials(db, web: dict, into_id: int) -> None:
    """Preserve a merged web account's email/OAuth logins on the surviving user."""
    target = await get_user(db, into_id)
    sets, params = [], []
    for col in ("auth_email", "password_hash", "google_sub", "apple_sub", "auth_user_id"):
        if web.get(col) and not (target and target.get(col)):
            sets.append(f"{col} = ?")
            params.append(web[col])
    if not sets:
        return
    params.append(into_id)
    await db.execute(f"UPDATE users SET {', '.join(sets)} WHERE telegram_id = ?", tuple(params))
    await db.commit()


@app.post("/api/auth/sync")
async def api_auth_sync(request: Request):
    """Link the Supabase Auth session to a public.users row and set the app cookie."""
    token = _bearer_token(request)
    if not token:
        raise HTTPException(401, "Missing access token")
    su = await verify_supabase_access_token(token)
    if not su:
        raise HTTPException(401, "Invalid session")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    invite_slug = (body.get("invite_slug") or "").strip().lower() or None

    db = await get_db()
    try:
        await ensure_schema()
        user = await ensure_app_user_from_supabase(db, su=su)
        if invite_slug:
            await _assign_group_from_slug(db, user["telegram_id"], invite_slug)
            user = await get_user(db, user["telegram_id"])
    finally:
        await db.close()
    return _session_response(user["telegram_id"])


@app.post("/api/auth/logout")
async def api_auth_logout():
    return Response(
        content=json.dumps({"ok": True}),
        media_type="application/json",
        headers={"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"},
    )


# ---------------------------------------------------------------------------
# /api/me
# ---------------------------------------------------------------------------

@app.get("/api/me")
async def api_me(request: Request):
    user, db = await _auth(request)
    cur = await db.execute(
        "SELECT type, amount FROM transactions WHERE user_id=?", (user["telegram_id"],)
    )
    txs = await cur.fetchall()
    lifetime_won   = sum(t["amount"] for t in txs if t["type"] == "win")
    lifetime_spent = sum(abs(t["amount"]) for t in txs if t["type"] == "participate")
    ctx = await enrich_user_context(db, user)
    invite_error = user.pop("_invite_error", None)
    await db.close()
    u = dict(user)
    return {
        **u,
        "balance": u["credit"],
        "first_name": u["full_name"],
        "photo_url": u.get("photo_url"),
        "stripe_enabled": bool(config.STRIPE_SECRET_KEY),
        "lifetime_won": lifetime_won,
        "lifetime_spent": lifetime_spent,
        **ctx,
        "invite_error": invite_error,
    }


@app.get("/api/group/preview")
async def api_group_preview(slug: str):
    db = await get_db()
    group = await get_group_by_slug(db, slug)
    if not group:
        await db.close()
        raise HTTPException(404, "Group not found")
    trustee = await get_trustee_user(db, group["trustee_user_id"])
    await db.close()
    return {
        "group": group_public(group),
        "trustee": trustee_public(trustee),
    }


@app.post("/api/group/join")
async def api_group_join(request: Request):
    user, db = await _auth(request)
    body = await request.json()
    slug = (body.get("slug") or "").strip().lower()
    if not slug:
        raise HTTPException(400, "slug required")
    err, _group = await join_group_by_slug(db, user["telegram_id"], slug)
    if err:
        await db.close()
        raise HTTPException(400, err)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    ctx = await enrich_user_context(db, dict(row))
    await db.close()
    return {"ok": True, **ctx}


@app.get("/api/groups")
async def api_groups_list(request: Request):
    user, db = await _auth(request)
    memberships = await get_user_groups(db, user["telegram_id"])
    active_gid = await ensure_active_group_id(db, user)
    await db.close()
    if not _bot_username:
        raise HTTPException(500, "Bot not available")
    groups = []
    for m in memberships:
        slug = m["slug"]
        groups.append({
            **member_group_public(m),
            "is_active": m["id"] == active_gid,
            "link": f"https://t.me/{_bot_username}?startapp=join_{slug}",
            "bot_link": f"https://t.me/{_bot_username}?start=g_{slug}",
        })
    return {"groups": groups, "active_group_id": active_gid}


@app.post("/api/groups/active")
async def api_groups_set_active(request: Request):
    user, db = await _auth(request)
    body = await request.json()
    group_id = body.get("group_id")
    if group_id is None:
        raise HTTPException(400, "group_id required")
    gid = int(group_id)
    if not await user_in_group(db, user["telegram_id"], gid):
        await db.close()
        raise HTTPException(403, "You are not a member of this group")
    await db.execute(
        "UPDATE users SET group_id = ? WHERE telegram_id = ?",
        (gid, user["telegram_id"]),
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    ctx = await enrich_user_context(db, dict(row))
    await db.close()
    return {"ok": True, **ctx}


# ---------------------------------------------------------------------------
# /api/invite
# ---------------------------------------------------------------------------

@app.get("/api/invite")
async def api_invite(request: Request, group_id: int | None = None):
    user, db = await _auth(request)
    gid = group_id or user.get("group_id")
    if not gid:
        gid = await ensure_active_group_id(db, user)
    if not gid or not await user_in_group(db, user["telegram_id"], gid):
        await db.close()
        raise HTTPException(403, "Join this group before sharing invites")
    group = await get_group(db, gid)
    if not group:
        await db.close()
        raise HTTPException(404, "Group not found")
    join_code = await ensure_join_code(db, group)
    await db.close()
    slug = group["slug"]
    app_link = f"https://t.me/{_bot_username}?startapp=join_{slug}" if _bot_username else None
    bot_link = f"https://t.me/{_bot_username}?start=g_{slug}" if _bot_username else None
    return {
        "link": app_link,
        "app_link": app_link,
        "bot_link": bot_link,
        "slug": slug,
        "join_code": join_code,
        "group_id": gid,
        "group_name": group["name"],
    }


@app.post("/api/group/join-code")
async def api_group_join_code(request: Request):
    user, db = await _auth(request)
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code:
        await db.close()
        raise HTTPException(400, "Enter a join code")
    err, group = await join_group_by_code(db, user["telegram_id"], code)
    if err:
        await db.close()
        raise HTTPException(400, err)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    ctx = await enrich_user_context(db, dict(row))
    await db.close()
    return {"ok": True, "group_name": group["name"], **ctx}


# ---------------------------------------------------------------------------
# /api/agreement
# ---------------------------------------------------------------------------

async def _trustee_for_user(db, user: dict):
    group = await get_group(db, user.get("group_id"))
    if not group:
        return None
    return await get_trustee_user(db, group["trustee_user_id"])


async def _group_pricing_plan(db, group_id) -> str:
    """The group's locked pricing plan ('subscription' | 'prize_share')."""
    if not group_id:
        return "subscription"
    cur = await db.execute("SELECT pricing_plan FROM groups WHERE id=?", (group_id,))
    row = await cur.fetchone()
    plan = row["pricing_plan"] if row else None
    return plan if plan in ("subscription", "prize_share") else "subscription"


async def _trustee_dict_for_user(db, user: dict) -> dict:
    row = await _trustee_for_user(db, user)
    if row:
        return build_trustee_from_user(dict(row))
    return build_trustee_from_user({
        "full_name": "Group Trustee",
        "street": None, "city": None, "province": None,
        "phone": None, "email": None,
    })


def _display_name(row) -> str:
    if not row:
        return "Group Trustee"
    return row["full_name"] or row["username"] or f"User {row['telegram_id']}"


def _beneficiary_agreement_kwargs(user: dict) -> dict:
    return {
        "beneficiary_name": user.get("full_name") or user.get("username") or f"User {user['telegram_id']}",
        "beneficiary_id": user["telegram_id"],
        "beneficiary_street": user.get("street"),
        "beneficiary_city": user.get("city"),
        "beneficiary_province": user.get("province"),
        "beneficiary_postal": user.get("postal_code"),
        "beneficiary_phone": user.get("phone"),
        "beneficiary_email": user.get("email"),
        "declaration_category": user.get("declaration_category"),
        "accepted_at": user.get("agreement_accepted_at"),
    }


async def _round_participant_count(db, round_id: int) -> int | None:
    """Number of paid beneficiaries recorded for a round (for the draw agreement)."""
    try:
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM participations WHERE round_id=?", (round_id,)
        )
        row = await cur.fetchone()
        return int(row["n"]) if row else None
    except Exception:
        return None


def _round_ticket_numbers_str(rd: dict) -> str | None:
    """Plain-text ticket numbers for the round agreement, once the ticket is bought."""
    raw = rd.get("ticket_numbers")
    if not raw:
        return None
    try:
        rows = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    if not rows:
        return None
    msg = format_ticket_numbers_message(rows, rd.get("lottery_type"))
    return re.sub(r"<[^>]+>", "", msg or "").strip() or None


def _beneficiary_update_parts(body: dict, user: dict) -> tuple[list[str], list]:
    """Build SET clauses only for fields present in the request body."""
    sets: list[str] = []
    params: list = []

    if "fullName" in body or "full_name" in body:
        val = (body.get("fullName") or body.get("full_name") or user.get("full_name") or "").strip()
        sets.append("full_name = COALESCE(NULLIF(?, ''), full_name)")
        params.append(val)

    if "email" in body:
        val = (body.get("email") or "").strip().lower()
        sets.append("email = COALESCE(NULLIF(?, ''), email)")
        params.append(val)

    for json_key, col in (
        ("street", "street"),
        ("city", "city"),
        ("province", "province"),
        ("postal", "postal_code"),
        ("phone", "phone"),
        ("category", "declaration_category"),
    ):
        if json_key in body:
            sets.append(f"{col} = COALESCE(?, {col})")
            params.append(body.get(json_key))

    if "acceptedAt" in body or "accepted_at" in body:
        sets.append("agreement_accepted_at = COALESCE(?, agreement_accepted_at)")
        params.append(body.get("acceptedAt") or body.get("accepted_at"))

    return sets, params


@app.patch("/api/profile/email")
async def api_update_profile_email(request: Request):
    """Save Interac e-transfer sender email only (Profile page)."""
    user, db = await _auth(request)
    body = await request.json()
    email_addr = (body.get("email") or "").strip().lower()
    if not email_addr or "@" not in email_addr:
        await db.close()
        raise HTTPException(400, "Valid email required")
    await db.execute(
        "UPDATE users SET email=? WHERE telegram_id=?", (email_addr, user["telegram_id"])
    )
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    await db.close()
    if not row or (row.get("email") or "").strip().lower() != email_addr:
        raise HTTPException(500, "Failed to save email")
    return {"ok": True, "email": email_addr, "user": dict(row)}


@app.post("/api/beneficiary")
async def api_save_beneficiary(request: Request):
    """Persist beneficiary profile from onboarding (BCLC Group Prize Agreement)."""
    user, db = await _auth(request)
    body = await request.json()
    sets, params = _beneficiary_update_parts(body, user)
    if not sets:
        await db.close()
        raise HTTPException(400, "No profile fields to update")
    params.append(user["telegram_id"])
    await db.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE telegram_id = ?",
        tuple(params),
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    await db.close()
    return {"ok": True, "user": dict(row) if row else None}


@app.get("/api/agreement/master")
async def api_agreement_master(request: Request):
    user, db = await _auth(request)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    u = dict(row) if row else dict(user)
    trustee = await _trustee_dict_for_user(db, u)
    plan = await _group_pricing_plan(db, u.get("group_id"))
    body = build_master_agreement(**_beneficiary_agreement_kwargs(u), trustee=trustee, pricing_plan=plan)
    await db.close()
    return {
        "title": "Group Prize Agreement",
        "body": body,
    }


@app.get("/api/agreement/download-token")
async def api_agreement_download_token(request: Request):
    """Mint a short link token so a download can be opened in an external
    browser (Telegram) that has no session cookie."""
    user, db = await _auth(request)
    await db.close()
    return {"token": create_session_token(user["telegram_id"])}


@app.get("/api/agreement/master/download")
async def api_agreement_master_download(request: Request):
    user, db = await _auth_with_query_token(request)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    u = dict(row) if row else dict(user)
    kwargs = _beneficiary_agreement_kwargs(u)
    trustee = await _trustee_dict_for_user(db, u)
    plan = await _group_pricing_plan(db, u.get("group_id"))
    body = build_master_agreement(**kwargs, trustee=trustee, pricing_plan=plan)
    await db.close()
    ben = kwargs["beneficiary_name"]
    addr = ", ".join(
        p for p in [
            u.get("street"),
            u.get("city"),
            u.get("province"),
            u.get("postal_code"),
        ] if p
    ) or "—"
    pdf_bytes = build_agreement_pdf(
        title="Group Prize Agreement",
        subtitle=f"Beneficiary: {ben} · Trustee: {trustee['name']}",
        body=body,
        highlights=[
            ("Trustee", trustee["name"]),
            ("Trustee email", trustee["email"]),
            ("Beneficiary", ben),
            ("Beneficiary address", addr),
        ],
        highlights_title="Parties",
        skip_sections=["LOTTO CHEE — GROUP TRUSTEE", "BENEFICIARY"],
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="lotto-chee-group-prize-agreement.pdf"'},
    )


@app.get("/api/agreement/round/{round_id}")
async def api_agreement_round(request: Request, round_id: int):
    user, db = await _auth(request)
    await _auto_close_round_if_due(db, round_id)
    cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_id,))
    round_ = await cur.fetchone()
    if not round_:
        await db.close()
        raise HTTPException(404, "Round not found")
    rd = dict(round_)
    if not agreement_available(rd["status"], rd.get("draw_date")):
        await db.close()
        raise HTTPException(403, "Round agreement available after entries close (1 day before draw)")
    cur = await db.execute(
        "SELECT * FROM participations WHERE round_id=? AND user_id=?",
        (round_id, user["telegram_id"]),
    )
    part = await cur.fetchone()
    if not part:
        await db.close()
        raise HTTPException(403, "Join this round to access your draw agreement")
    pool = rd.get("pool") or 0
    share_pct = round(part["amount"] / pool * 100, 1) if pool else None
    trustee = await _trustee_dict_for_user(db, user)
    pcount = await _round_participant_count(db, round_id)
    tnums = _round_ticket_numbers_str(rd)
    body = build_round_agreement(
        round_id=round_id,
        lottery_type=rd.get("lottery_type"),
        draw_date=rd.get("draw_date"),
        beneficiary_name=user.get("full_name") or user.get("username") or f"User {user['telegram_id']}",
        shares=part.get("shares") or 1,
        stake_amount=part["amount"],
        pool_amount=pool,
        share_pct=share_pct,
        closed_at=rd.get("closed_at"),
        trustee=trustee,
        participants_count=pcount,
        ticket_numbers=tnums,
    )
    await db.close()
    return {
        "title": f"Round #{round_id} Draw Agreement",
        "body": body,
        "round_id": round_id,
    }


@app.get("/api/agreement/round/{round_id}/download")
async def api_agreement_round_download(request: Request, round_id: int):
    user, db = await _auth_with_query_token(request)
    await _auto_close_round_if_due(db, round_id)
    # Look up by id and authorize via participation below — not by the user's
    # active group_id (a participant may belong to several groups).
    cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_id,))
    round_ = await cur.fetchone()
    if not round_:
        await db.close()
        raise HTTPException(404, "Round not found")
    rd = dict(round_)
    if not agreement_available(rd["status"], rd.get("draw_date")):
        await db.close()
        raise HTTPException(403, "Round agreement available after entries close (1 day before draw)")
    cur = await db.execute(
        "SELECT * FROM participations WHERE round_id=? AND user_id=?",
        (round_id, user["telegram_id"]),
    )
    part = await cur.fetchone()
    if not part:
        await db.close()
        raise HTTPException(403, "Join this round to access your draw agreement")
    pool = rd.get("pool") or 0
    share_pct = round(part["amount"] / pool * 100, 1) if pool else None
    beneficiary_name = user.get("full_name") or user.get("username") or f"User {user['telegram_id']}"
    trustee = await _trustee_dict_for_user(db, user)
    pcount = await _round_participant_count(db, round_id)
    tnums = _round_ticket_numbers_str(rd)
    body = build_round_agreement(
        round_id=round_id,
        lottery_type=rd.get("lottery_type"),
        draw_date=rd.get("draw_date"),
        beneficiary_name=beneficiary_name,
        shares=part.get("shares") or 1,
        stake_amount=part["amount"],
        pool_amount=pool,
        share_pct=share_pct,
        closed_at=rd.get("closed_at"),
        trustee=trustee,
        participants_count=pcount,
        ticket_numbers=tnums,
    )
    await db.close()
    pct_line = f"{share_pct}%" if share_pct is not None else "—"
    pdf_bytes = build_agreement_pdf(
        title=f"Round #{round_id} Draw Agreement",
        subtitle=f"Addendum · {lottery_label(rd.get('lottery_type'))} · Draw {rd.get('draw_date') or 'TBD'}",
        body=body,
        highlights=[
            ("Beneficiary", beneficiary_name),
            ("Shares", str(part.get("shares") or 1)),
            ("Stake", f"${part['amount']:.2f} CAD"),
            ("Pool share", f"{pct_line} of ${pool:.2f}"),
        ],
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="lotto-chee-round-{round_id}-agreement.pdf"'
        },
    )


# ---------------------------------------------------------------------------
# /api/round
# ---------------------------------------------------------------------------

async def _try_fetch_round_jackpot(rd: dict) -> int | None:
    """Return estimated jackpot from lotto site when this round is the next draw."""
    draw_date_str = rd.get("draw_date")
    if not draw_date_str:
        return None
    lt = rd.get("lottery_type") or "lotto_max"
    next_draw = next_draw_date(lt)
    if not next_draw or draw_date_str != next_draw.isoformat():
        return None
    return await fetch_estimated_jackpot(lt)


async def _maybe_refresh_round_jackpot(db, rd: dict) -> None:
    """Persist estimated jackpot when a round's draw becomes the next one."""
    if rd.get("jackpot") or rd.get("status") not in ("open", "closed"):
        return
    jackpot = await _try_fetch_round_jackpot(rd)
    if not jackpot:
        return
    await db.execute("UPDATE rounds SET jackpot=? WHERE id=?", (jackpot, rd["id"]))
    await db.commit()
    rd["jackpot"] = jackpot


def _round_jackpot_fetchable(rd: dict) -> bool:
    if rd.get("jackpot"):
        return False
    if rd.get("status") not in ("open", "closed"):
        return False
    draw_date_str = rd.get("draw_date")
    if not draw_date_str:
        return False
    lt = rd.get("lottery_type") or "lotto_max"
    next_draw = next_draw_date(lt)
    return bool(next_draw and draw_date_str == next_draw.isoformat())


async def _build_round_detail(db, round_, user_id: int) -> dict:
    await _auto_close_round_if_due(db, round_["id"])
    cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_["id"],))
    refreshed = await cur.fetchone()
    if refreshed:
        round_ = refreshed
    rd = dict(round_)
    await _maybe_refresh_round_jackpot(db, rd)
    cur = await db.execute(
        "SELECT p.*, u.username, u.full_name FROM participations p "
        "JOIN users u ON u.telegram_id=p.user_id WHERE p.round_id=? ORDER BY p.amount DESC",
        (rd["id"],),
    )
    parts = [dict(r) for r in await cur.fetchall()]
    pool = rd.get("pool") or sum(p["amount"] for p in parts)
    for p in parts:
        p["pct"] = round(p["amount"] / pool * 100, 1) if pool else 0
        p["won"] = (rd.get("winner_id") == p["user_id"])
    my = next((p for p in parts if p["user_id"] == user_id), None)
    rd["participants"] = parts
    rd["participants_count"] = len(parts)
    rd["pool"] = pool
    rd["my_stake"]  = my["amount"] if my else None
    rd["my_shares"] = (my.get("shares") if my else None) or (round(my["amount"] / (rd.get("price_per_share") or 5)) if my else None)
    rd["my_prize"]  = my["prize"]  if my else None
    rd["my_free_tickets"] = (my.get("free_tickets_awarded") or 0) if my else None
    rd["my_pct"]    = my["pct"]    if my else None
    rd["my_won"]    = my["won"]    if my else None
    rd["pool_target"] = ((rd.get("tickets_target") or 0) * (rd.get("price_per_share") or 5)) or None
    rd["tickets_required"] = await _round_tickets_required(db, rd)
    saved = parse_round_tickets(rd.get("round_tickets"), rd.get("lottery_type"))
    all_rows = merge_round_ticket_rows(saved)
    lt = rd.get("lottery_type")
    rd["tickets_uploaded"] = count_tickets(all_rows, lt)
    rd["rows_per_ticket"] = rows_per_ticket(lt)
    rd["round_tickets"] = saved
    rd["tickets_breakdown"] = _ticket_breakdown_for_round(rd, all_rows)
    rd.pop("ticket_results", None)
    ticket_images = [t["image"] for t in saved if t.get("image")]
    if not ticket_images and rd.get("ticket_image"):
        ticket_images = [rd["ticket_image"]]
    rd["ticket_images"] = ticket_images
    rd["has_ticket_image"] = bool(ticket_images)
    rd.pop("ticket_image", None)
    rd["display_status"] = display_status(
        rd["status"], rd.get("draw_date"),
        my_prize=rd.get("my_prize"), my_stake=rd.get("my_stake"),
        my_free_tickets=rd.get("my_free_tickets"),
        winning_numbers=rd.get("winning_numbers"), drawn_at=rd.get("drawn_at"),
    )
    rd["entries_open"] = entries_open(rd["status"], rd.get("draw_date"))
    rd["agreement_available"] = agreement_available(rd["status"], rd.get("draw_date"))
    rd["results_finalized"] = results_finalized(
        rd["status"], rd.get("winning_numbers"), rd.get("drawn_at")
    )
    if rd.get("winner_id"):
        cur = await db.execute(
            "SELECT full_name, username FROM users WHERE telegram_id=?", (rd["winner_id"],)
        )
        w = await cur.fetchone()
        rd["winner_name"] = (w["full_name"] or w["username"]) if w else None
    else:
        rd["winner_name"] = None
    rd["jackpot_pending"] = not rd.get("jackpot")
    rd["jackpot_fetchable"] = _round_jackpot_fetchable(rd)
    return rd


_OPEN_ROUNDS_ORDER = (
    "CASE WHEN draw_date IS NULL THEN 1 ELSE 0 END, draw_date ASC, id ASC"
)


async def _require_active_member_group(user: dict, db) -> int:
    gid = await ensure_active_group_id(db, user)
    if not gid:
        raise HTTPException(403, "Join a group to play")
    group = await get_group(db, gid)
    if not group:
        raise HTTPException(403, "Group not found")
    if group["status"] != "active":
        raise HTTPException(403, "This group is not active")
    return gid


async def _active_group_row(user: dict, db):
    gid = await _require_active_member_group(user, db)
    return gid, await get_group(db, gid)


def _payment_options_payload(group, *, stripe_configured: bool) -> dict:
    admin_email = (group.get("etransfer_email") if group else None) or config.ADMIN_ETRANSFER_EMAIL
    min_amt = float(group.get("etransfer_min_amount") or 25) if group else 25.0
    # Card top-ups route to the trustee's connected Stripe account, so card is
    # only usable once that account is connected and can accept charges.
    connect_ready = bool(group and group.get("stripe_account_id") and group.get("stripe_charges_enabled"))
    card_setting = bool(group and group_allows_payment(group, "card") and stripe_configured)
    card_allowed = card_setting and connect_ready
    etx_allowed = bool(group and group_allows_payment(group, "etransfer") and admin_email)
    etx_presets = [a for a in CARD_DEPOSIT_AMOUNTS if a >= min_amt]
    return {
        "payment_methods": group_public(group)["payment_methods"] if group else "both",
        "etransfer_min_amount": min_amt,
        "card_amounts": list(CARD_DEPOSIT_AMOUNTS),
        "etransfer_amounts": etx_presets,
        "card_enabled": card_allowed,
        "card_connect": connect_ready,
        "card_setup_pending": card_setting and not connect_ready,
        "etransfer_enabled": etx_allowed,
        "etransfer_email": admin_email if etx_allowed else None,
    }


@app.get("/api/round")
async def api_round(request: Request):
    user, db = await _auth(request)
    gid = await _require_active_member_group(user, db)
    await _auto_close_all_due_rounds(db)
    cur = await db.execute(
        f"SELECT * FROM rounds WHERE status='open' AND group_id=? ORDER BY {_OPEN_ROUNDS_ORDER} LIMIT 1",
        (gid,),
    )
    round_ = await cur.fetchone()
    if round_ is None:
        cur = await db.execute(
            "SELECT * FROM rounds WHERE group_id=? ORDER BY id DESC LIMIT 1", (gid,)
        )
        round_ = await cur.fetchone()
    if round_ is None:
        await db.close()
        return {"round": None}
    rd = await _build_round_detail(db, round_, user["telegram_id"])
    await db.close()
    return {"round": rd}


@app.get("/api/rounds/open")
async def api_open_rounds(request: Request):
    user, db = await _auth(request)
    gid = await _require_active_member_group(user, db)
    await _auto_close_all_due_rounds(db)
    cur = await db.execute(
        f"SELECT * FROM rounds WHERE status='open' AND group_id=? ORDER BY {_OPEN_ROUNDS_ORDER}",
        (gid,),
    )
    rows = await cur.fetchall()
    rounds = [await _build_round_detail(db, r, user["telegram_id"]) for r in rows]
    await db.close()
    return {"rounds": rounds}


# ---------------------------------------------------------------------------
# /api/rounds  (NEW)
# ---------------------------------------------------------------------------

@app.get("/api/rounds")
async def api_rounds(request: Request):
    user, db = await _auth(request)
    gid = await _require_active_member_group(user, db)
    await _auto_close_all_due_rounds(db)
    cur = await db.execute("""
        SELECT r.*,
          p.amount as my_stake, p.shares as my_shares, p.prize as my_prize,
          (SELECT COUNT(*) FROM participations WHERE round_id=r.id) as participants_count
        FROM rounds r
        LEFT JOIN participations p ON p.round_id=r.id AND p.user_id=?
        WHERE r.group_id = ?
        ORDER BY r.id DESC LIMIT 20
    """, (user["telegram_id"], gid))
    rounds = []
    for row in await cur.fetchall():
        rd = dict(row)
        rd["display_status"] = display_status(
            rd["status"], rd.get("draw_date"),
            my_prize=rd.get("my_prize"), my_stake=rd.get("my_stake"),
            winning_numbers=rd.get("winning_numbers"), drawn_at=rd.get("drawn_at"),
        )
        rd["entries_open"] = entries_open(rd["status"], rd.get("draw_date"))
        rd["agreement_available"] = agreement_available(rd["status"], rd.get("draw_date"))
        rd["results_finalized"] = results_finalized(
            rd["status"], rd.get("winning_numbers"), rd.get("drawn_at")
        )
        rd["pool_target"] = ((rd.get("tickets_target") or 0) * (rd.get("price_per_share") or 5)) or None
        rd["participants_count"] = int(rd.get("participants_count") or 0)
        rd["participants"] = rd["participants_count"]
        rd["my_pct"] = round((rd["my_stake"] / rd["pool"]) * 100, 1) if rd.get("my_stake") and rd.get("pool") else None
        saved = parse_round_tickets(rd.get("round_tickets"), rd.get("lottery_type"))
        ticket_images = [t["image"] for t in saved if t.get("image")]
        if not ticket_images and rd.get("ticket_image"):
            ticket_images = [rd["ticket_image"]]
        rd["ticket_images"] = ticket_images
        rd["has_ticket_image"] = bool(ticket_images)
        rd["rows_per_ticket"] = rows_per_ticket(rd.get("lottery_type"))
        rd["tickets_breakdown"] = _ticket_breakdown_for_round(
            rd, merge_round_ticket_rows(saved)
        )
        rd.pop("ticket_image", None)
        rd.pop("round_tickets", None)
        rd.pop("ticket_results", None)
        rounds.append(rd)
    await db.close()
    return {"rounds": rounds}


# ---------------------------------------------------------------------------
# /api/participate
# ---------------------------------------------------------------------------

@app.post("/api/participate")
async def api_participate(request: Request):
    user, db = await _auth(request)
    gid = await _require_active_member_group(user, db)
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    round_id = body.get("round_id")
    if round_id:
        cur = await db.execute(
            "SELECT * FROM rounds WHERE id=? AND group_id=?", (int(round_id), gid)
        )
    else:
        cur = await db.execute(
            f"SELECT * FROM rounds WHERE status='open' AND group_id=? ORDER BY {_OPEN_ROUNDS_ORDER} LIMIT 1",
            (gid,),
        )
    round_ = await cur.fetchone()
    if round_ is None:
        raise HTTPException(400, "No open round")
    round_d = dict(round_)
    await _auto_close_round_if_due(db, round_d["id"])
    cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_d["id"],))
    round_ = await cur.fetchone()
    if round_ is None:
        raise HTTPException(400, "Round not found")
    round_d = dict(round_)
    if not entries_open(round_d["status"], round_d.get("draw_date")):
        raise HTTPException(400, "Entries closed — draw agreement is available in Rounds")
    if user["credit"] < amount:
        raise HTTPException(
            400,
            f"Not enough credit (${user['credit']:.2f} available, ${amount:.2f} needed). "
            "Top up on Home first, then join again.",
        )
    price_per_share = dict(round_).get("price_per_share") or 5.0
    shares = max(1, round(amount / price_per_share))
    # Upsert: allow adding more stake to same round
    cur = await db.execute(
        "SELECT * FROM participations WHERE round_id=? AND user_id=?",
        (round_["id"], user["telegram_id"])
    )
    existing = await cur.fetchone()
    if existing:
        new_shares = (existing["shares"] or 0) + shares
        await db.execute(
            "UPDATE participations SET amount=amount+?, shares=? WHERE round_id=? AND user_id=?",
            (amount, new_shares, round_["id"], user["telegram_id"])
        )
    else:
        await db.execute(
            "INSERT INTO participations (round_id, user_id, amount, shares) VALUES (?,?,?,?)",
            (round_["id"], user["telegram_id"], amount, shares)
        )
    await db.execute("UPDATE rounds SET pool=pool+? WHERE id=?", (amount, round_["id"]))
    await db.execute("UPDATE users SET credit=credit-? WHERE telegram_id=?", (amount, user["telegram_id"]))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
        (user["telegram_id"], "participate", -amount, f"Round #{round_['id']}", gid),
    )
    await db.commit()
    cur = await db.execute("SELECT pool FROM rounds WHERE id=?", (round_["id"],))
    row = await cur.fetchone()
    pool = row["pool"] if row else amount
    cur = await db.execute(
        "SELECT amount FROM participations WHERE round_id=? AND user_id=?",
        (round_["id"], user["telegram_id"])
    )
    my = await cur.fetchone()
    my_pct = round((my["amount"] / pool) * 100, 1) if my and pool else 0
    round_d["pool"] = pool
    await _notify_round_contribution(db, round_d, user)
    await db.close()
    return {"ok": True, "my_pct": my_pct}


# ---------------------------------------------------------------------------
# /api/transactions
# ---------------------------------------------------------------------------

@app.get("/api/transactions")
async def api_transactions(request: Request):
    user, db = await _auth(request)
    cur = await db.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 50", (user["telegram_id"],)
    )
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"transactions": rows}


# ---------------------------------------------------------------------------
# /api/deposit  (manual / admin-approved)
# ---------------------------------------------------------------------------

@app.post("/api/deposit")
async def api_deposit(request: Request):
    user, db = await _auth(request)
    gid = await _require_active_member_group(user, db)
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    await db.execute(
        "INSERT INTO deposit_requests (user_id, amount, group_id) VALUES (?,?,?)",
        (user["telegram_id"], amount, gid),
    )
    await db.commit()
    await db.close()
    return {"ok": True, "message": "Deposit request submitted for approval"}


# ---------------------------------------------------------------------------
# /api/settings
# ---------------------------------------------------------------------------

_SETTING_DEFAULTS = dict(
    auto_participate=False, shares_per_round=1, max_rounds_per_month=4,
    preferred_day=None, lottery_preference="both",
    notif_new_round=True, notif_reminder=True, notif_ticket=True, notif_results=True,
    notif_contribution=True, notif_round_closed=True,
)

_LOTTERY_SHARE_PRICE = LOTTERY_PREFERENCE_PRICES


def _row_get(row, key, default=None):
    """Safe column access for DB rows that may predate a newly-added column."""
    try:
        val = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if val is None else val


def _row_to_settings(row) -> dict:
    if row is None:
        return {**_SETTING_DEFAULTS}
    return {
        "auto_participate":     bool(row["auto_participate"]),
        "shares_per_round":     row["shares_per_round"],
        "max_rounds_per_month": row["max_rounds_per_month"],
        "preferred_day":        row["preferred_day"],
        "lottery_preference":   row["lottery_preference"] or "both",
        "notif_new_round":      bool(row["notif_new_round"]),
        "notif_reminder":       bool(row["notif_reminder"]),
        "notif_ticket":         bool(row["notif_ticket"]),
        "notif_results":        bool(row["notif_results"]),
        "notif_contribution":   bool(_row_get(row, "notif_contribution", 1)),
        "notif_round_closed":   bool(_row_get(row, "notif_round_closed", 1)),
    }


@app.get("/api/settings")
async def get_settings(request: Request):
    user, db = await _auth(request)
    cur = await db.execute("SELECT * FROM user_settings WHERE user_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    await db.close()
    return _row_to_settings(row)


@app.put("/api/settings")
async def put_settings(request: Request):
    user, db = await _auth(request)
    b = await request.json()
    lottery_pref = b.get("lottery_preference", "both")
    if lottery_pref not in _LOTTERY_SHARE_PRICE:
        lottery_pref = "both"
    await db.execute("""
        INSERT INTO user_settings
            (user_id, auto_participate, shares_per_round, max_rounds_per_month,
             preferred_day, lottery_preference,
             notif_new_round, notif_reminder, notif_ticket, notif_results,
             notif_contribution, notif_round_closed, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            auto_participate=excluded.auto_participate,
            shares_per_round=excluded.shares_per_round,
            max_rounds_per_month=excluded.max_rounds_per_month,
            preferred_day=excluded.preferred_day,
            lottery_preference=excluded.lottery_preference,
            notif_new_round=excluded.notif_new_round,
            notif_reminder=excluded.notif_reminder,
            notif_ticket=excluded.notif_ticket,
            notif_results=excluded.notif_results,
            notif_contribution=excluded.notif_contribution,
            notif_round_closed=excluded.notif_round_closed,
            updated_at=excluded.updated_at
    """, (
        user["telegram_id"],
        int(bool(b.get("auto_participate", False))),
        max(1, int(b.get("shares_per_round", 1))),
        max(1, int(b.get("max_rounds_per_month", 4))),
        b.get("preferred_day"),
        lottery_pref,
        int(bool(b.get("notif_new_round",  True))),
        int(bool(b.get("notif_reminder",   True))),
        int(bool(b.get("notif_ticket",     True))),
        int(bool(b.get("notif_results",    True))),
        int(bool(b.get("notif_contribution", True))),
        int(bool(b.get("notif_round_closed", True))),
    ))
    await db.commit()
    await db.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# E-transfer endpoints
# ---------------------------------------------------------------------------

@app.get("/api/payment/options")
async def payment_options(request: Request):
    user, db = await _auth(request)
    try:
        _, group = await _active_group_row(user, db)
    except HTTPException:
        group = await get_group(db, user.get("group_id")) if user.get("group_id") else None
    payload = _payment_options_payload(group, stripe_configured=bool(config.STRIPE_SECRET_KEY))
    await db.close()
    return payload


@app.get("/api/etransfer/info")
async def etransfer_info(request: Request):
    user, db = await _auth(request)
    try:
        _, group = await _active_group_row(user, db)
    except HTTPException:
        group = await get_group(db, user.get("group_id")) if user.get("group_id") else None
    opts = _payment_options_payload(group, stripe_configured=bool(config.STRIPE_SECRET_KEY))
    await db.close()
    return {
        "enabled": opts["etransfer_enabled"],
        "email": opts["etransfer_email"],
        "min_amount": opts["etransfer_min_amount"],
        "amounts": opts["etransfer_amounts"],
    }


@app.post("/api/etransfer/deposit")
async def etransfer_deposit(request: Request):
    user, db = await _auth(request)
    gid, group = await _active_group_row(user, db)
    body = await request.json()
    amount = round(float(body.get("amount", 0)), 2)
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    opts = _payment_options_payload(group, stripe_configured=bool(config.STRIPE_SECRET_KEY))
    if not opts["etransfer_enabled"]:
        await db.close()
        raise HTTPException(400, "E-transfer is not enabled for this group")
    min_amt = opts["etransfer_min_amount"]
    if amount < min_amt:
        await db.close()
        raise HTTPException(400, f"Minimum e-transfer amount is ${min_amt:.2f}")
    if not user.get("email"):
        await db.close()
        raise HTTPException(400, "Add your e-transfer email in Profile before sending a deposit")
    admin_email = opts["etransfer_email"]
    cur = await db.execute(
        "INSERT INTO deposit_requests (user_id, amount, payment_method, group_id) VALUES (?,?,'etransfer',?) RETURNING id",
        (user["telegram_id"], amount, gid),
    )
    dep_id = cur.lastrowid
    ref_code = f"LOTTO-{dep_id}"
    await db.execute("UPDATE deposit_requests SET ref_code=? WHERE id=?", (ref_code, dep_id))
    await db.commit()
    await db.close()
    return {
        "ok": True,
        "deposit_id": dep_id,
        "ref_code": ref_code,
        "amount": amount,
        "admin_email": admin_email,
    }


# ---------------------------------------------------------------------------
# Trustee application
# ---------------------------------------------------------------------------

TRUSTEE_AUTO_APPROVE_HOURS = 24


async def _approve_trustee_application(db, app_row, reviewed_by=None):
    """Create a group from a pending trustee application."""
    plan = app_row["pricing_plan"] if "pricing_plan" in app_row.keys() else None
    if plan not in ("subscription", "prize_share"):
        plan = "subscription"
    if plan == "subscription" and (app_row.get("payment_status") or "none") != "paid":
        raise HTTPException(400, "Subscription payment required before approval")

    applicant_id = app_row["applicant_user_id"]
    base_slug = slugify(app_row["proposed_group_name"])
    slug = base_slug
    n = 0
    while True:
        cur = await db.execute("SELECT id FROM groups WHERE slug=?", (slug,))
        if not await cur.fetchone():
            break
        n += 1
        slug = f"{base_slug}-{n}"
    join_code = generate_join_code()
    while True:
        cur = await db.execute("SELECT 1 FROM groups WHERE join_code=?", (join_code,))
        if not await cur.fetchone():
            break
        join_code = generate_join_code()

    platform_sub_id = app_row.get("stripe_sub_id") if plan == "subscription" else None
    platform_sub_status = (
        "active"
        if plan == "subscription" and platform_sub_id and app_row.get("payment_status") == "paid"
        else "none"
    )
    cur = await db.execute(
        """INSERT INTO groups (name, slug, trustee_user_id, status, join_code, pricing_plan,
           platform_sub_id, platform_sub_status)
           VALUES (?,?,?, 'active', ?, ?, ?, ?) RETURNING id""",
        (
            app_row["proposed_group_name"],
            slug,
            applicant_id,
            join_code,
            plan,
            platform_sub_id,
            platform_sub_status,
        ),
    )
    group_id = cur.lastrowid
    await db.execute(
        "UPDATE users SET group_id=? WHERE telegram_id=?", (group_id, applicant_id)
    )
    await add_group_member(db, group_id, applicant_id, "trustee")
    await db.execute(
        """UPDATE trustee_applications SET status='approved', reviewed_by=?,
           reviewed_at=datetime('now') WHERE id=?""",
        (reviewed_by, app_row["id"]),
    )
    return {"group_id": group_id, "slug": slug}


async def _maybe_auto_approve_applications(db):
    cur = await db.execute(
        """SELECT * FROM trustee_applications
           WHERE status='pending' AND payment_status='paid'
             AND auto_approve_at IS NOT NULL AND auto_approve_at <= datetime('now')"""
    )
    rows = await cur.fetchall()
    for app_row in rows:
        await _approve_trustee_application(db, app_row, reviewed_by=None)
    if rows:
        await db.commit()


@app.get("/api/trustee/application")
async def api_trustee_application_status(request: Request):
    user, db = await _auth(request)
    await ensure_schema()
    await _maybe_auto_approve_applications(db)
    cur = await db.execute(
        """SELECT * FROM trustee_applications
           WHERE applicant_user_id = ? ORDER BY id DESC LIMIT 1""",
        (user["telegram_id"],),
    )
    app_row = await cur.fetchone()
    await db.close()
    return {"application": dict(app_row) if app_row else None}


@app.post("/api/trustee/apply")
async def api_trustee_apply(request: Request):
    user, db = await _auth(request)
    await ensure_schema()
    if await trustee_group_id(db, user):
        await db.close()
        raise HTTPException(400, "You already manage a group")
    cur = await db.execute(
        "SELECT id FROM trustee_applications WHERE applicant_user_id=? AND status='pending'",
        (user["telegram_id"],),
    )
    if await cur.fetchone():
        await db.close()
        raise HTTPException(400, "Application already pending")
    body = await request.json()
    name = (body.get("proposed_group_name") or body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Group name required")
    plan = body.get("pricing_plan") or "subscription"
    if plan not in ("subscription", "prize_share"):
        plan = "subscription"
    await db.execute(
        """INSERT INTO trustee_applications
           (applicant_user_id, proposed_group_name, pricing_plan, payment_status)
           VALUES (?,?,?, 'none')""",
        (user["telegram_id"], name, plan),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


@app.post("/api/trustee/application/subscription/create")
async def api_trustee_application_subscription_create(request: Request):
    """Start $6.99/mo subscription for a pending subscription-plan application."""
    user, db = await _auth(request)
    await ensure_schema()
    if not config.STRIPE_SECRET_KEY:
        await db.close()
        raise HTTPException(400, "Stripe not configured")
    cur = await db.execute(
        """SELECT * FROM trustee_applications
           WHERE applicant_user_id=? AND status='pending' ORDER BY id DESC LIMIT 1""",
        (user["telegram_id"],),
    )
    app_row = await cur.fetchone()
    if not app_row:
        await db.close()
        raise HTTPException(404, "No pending application")
    plan = app_row.get("pricing_plan") or "subscription"
    if plan != "subscription":
        await db.close()
        raise HTTPException(400, "Subscription payment is not required for this plan")
    if (app_row.get("payment_status") or "none") == "paid":
        await db.close()
        raise HTTPException(400, "Subscription already paid")

    existing_sub_id = app_row.get("stripe_sub_id")
    if existing_sub_id:
        try:
            sub = stripe.Subscription.retrieve(
                existing_sub_id, expand=["latest_invoice.payment_intent"]
            )
            pi = sub.latest_invoice.payment_intent
            if pi and pi.status in (
                "requires_payment_method",
                "requires_confirmation",
                "requires_action",
            ):
                await db.close()
                return {
                    "client_secret": pi.client_secret,
                    "subscription_id": existing_sub_id,
                    "price": GROUP_SUB_PRICE,
                }
        except Exception:
            pass

    try:
        customer_id = await _get_or_create_customer(user, db)
        price = stripe.Price.create(
            unit_amount=int(round(GROUP_SUB_PRICE * 100)),
            currency=config.CURRENCY.lower(),
            recurring={"interval": "month"},
            product_data={
                "name": f"LottoChee group plan — {app_row['proposed_group_name']}",
            },
        )
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            expand=["latest_invoice.payment_intent"],
            metadata={
                "kind": "application_sub",
                "application_id": str(app_row["id"]),
                "trustee_id": str(user["telegram_id"]),
            },
        )
        await db.execute(
            """UPDATE trustee_applications SET stripe_sub_id=?, payment_status='pending'
               WHERE id=?""",
            (sub.id, app_row["id"]),
        )
        await db.commit()
        cs = sub.latest_invoice.payment_intent.client_secret
        await db.close()
        return {"client_secret": cs, "subscription_id": sub.id, "price": GROUP_SUB_PRICE}
    except Exception as e:
        await db.close()
        log.exception("application subscription create error: %s", e)
        msg = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Subscription error: {msg}")


# ---------------------------------------------------------------------------
# Admin endpoints (group trustee)
# ---------------------------------------------------------------------------

@app.get("/api/admin/group")
async def admin_get_group(request: Request):
    user, db, group = await _require_group_trustee(request, allow_locked=True)
    await db.close()
    return {
        "group": {
            **group_public(group),
            "stripe_configured": bool(config.STRIPE_SECRET_KEY),
        }
    }


@app.patch("/api/admin/group")
async def admin_patch_group(request: Request):
    user, db, group = await _require_group_trustee(request)
    try:
        body = await request.json()
    except Exception:
        await db.close()
        raise HTTPException(400, "Invalid JSON body")
    gid = group["id"]

    try:
        await ensure_schema()
        return await _admin_patch_group_body(db, gid, body)
    except HTTPException:
        await db.close()
        raise
    except Exception as e:
        log.exception("admin_patch_group failed for group %s", gid)
        await db.close()
        err = str(e).lower()
        if "free_ticket_mode" in err and ("does not exist" in err or "undefined_column" in err):
            raise HTTPException(
                503,
                "Database is missing free_ticket_mode — restart the API after migrations, "
                "or run migrations/008_free_ticket_settings.sql in Supabase.",
            ) from e
        raise HTTPException(500, "Could not save group settings") from e


async def _admin_patch_group_body(db, gid: int, body: dict):
    if "payment_methods" in body:
        pm = (body.get("payment_methods") or "both").lower()
        if pm not in VALID_PAYMENT_METHODS:
            await db.close()
            raise HTTPException(400, "payment_methods must be etransfer, card, or both")
        await db.execute(
            "UPDATE groups SET payment_methods=? WHERE id=?", (pm, gid)
        )

    if "etransfer_min_amount" in body:
        try:
            min_amt = float(body["etransfer_min_amount"])
        except (TypeError, ValueError):
            await db.close()
            raise HTTPException(400, "Invalid etransfer_min_amount")
        if min_amt <= 0:
            await db.close()
            raise HTTPException(400, "etransfer_min_amount must be positive")
        await db.execute(
            "UPDATE groups SET etransfer_min_amount=? WHERE id=?", (min_amt, gid)
        )

    if "etransfer_email" in body:
        email = (body.get("etransfer_email") or "").strip().lower() or None
        await db.execute(
            "UPDATE groups SET etransfer_email=? WHERE id=?", (email, gid)
        )

    if "free_ticket_mode" in body:
        mode = normalize_free_ticket_mode(body.get("free_ticket_mode"))
        await db.execute(
            "UPDATE groups SET free_ticket_mode=? WHERE id=?", (mode, gid)
        )

    for col, key in (("reminder_hours_1", "reminder_hours_1"), ("reminder_hours_2", "reminder_hours_2")):
        if key in body:
            try:
                hrs = int(body[key])
            except (TypeError, ValueError):
                await db.close()
                raise HTTPException(400, f"Invalid {key}")
            if not (1 <= hrs <= 336):
                await db.close()
                raise HTTPException(400, f"{key} must be between 1 and 336 hours")
            await db.execute(f"UPDATE groups SET {col}=? WHERE id=?", (hrs, gid))

    await db.commit()
    cur = await db.execute("SELECT * FROM groups WHERE id=?", (gid,))
    updated = await cur.fetchone()
    await db.close()
    return {
        "ok": True,
        "group": {
            **group_public(updated),
            "stripe_configured": bool(config.STRIPE_SECRET_KEY),
        },
    }


@app.get("/api/admin/round")
async def admin_round(request: Request):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    cur = await db.execute(
        "SELECT * FROM rounds WHERE group_id=? ORDER BY id DESC LIMIT 1", (gid,)
    )
    round_ = await cur.fetchone()
    if round_ is None:
        await db.close()
        return {"round": None}
    rd = await _build_round_detail(db, round_, user["telegram_id"])
    cur2 = await db.execute("SELECT ticket_image FROM rounds WHERE id=?", (rd["id"],))
    img_row = await cur2.fetchone()
    if img_row and img_row["ticket_image"]:
        ti = img_row["ticket_image"]
        rd["ticket_image"] = ti if ti.startswith("http") else f"data:image/jpeg;base64,{ti}"
    await db.close()
    return {"round": rd}


@app.get("/api/admin/rounds")
async def admin_rounds(request: Request):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    cur = await db.execute(
        "SELECT * FROM rounds WHERE group_id=? AND status IN ('open','closed','uploaded','drawn') "
        "ORDER BY id DESC",
        (gid,),
    )
    rows = await cur.fetchall()
    rounds = []
    for row in rows:
        rd = await _build_round_detail(db, row, user["telegram_id"])
        cur2 = await db.execute("SELECT ticket_image FROM rounds WHERE id=?", (rd["id"],))
        img_row = await cur2.fetchone()
        if img_row and img_row["ticket_image"]:
            ti = img_row["ticket_image"]
            rd["ticket_image"] = ti if ti.startswith("http") else f"data:image/jpeg;base64,{ti}"
        rounds.append(rd)
    await db.close()
    return {"rounds": rounds}


@app.get("/api/admin/round/suggest")
async def admin_suggest_round(
    request: Request,
    lottery_type: str = "lotto_max",
    draw_date: str | None = None,
):
    """Suggest draw date and estimated jackpot for a new round."""
    _, db, _ = await _require_group_trustee(request)
    await db.close()
    if not valid_lottery_type(lottery_type):
        raise HTTPException(400, "Unknown lottery type")
    return await suggest_new_round(lottery_type, draw_date=draw_date)


@app.post("/api/admin/round/new")
async def admin_new_round(request: Request):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    # tickets_target 0 (or blank) means "no limit" — store 0.
    try:
        tickets_target = int(body.get("tickets_target") or 0)
    except (TypeError, ValueError):
        tickets_target = 0
    if tickets_target < 0:
        tickets_target = 0
    price_per_share = body.get("price_per_share") or 5.0
    draw_date = body.get("draw_date") or None
    lottery_type = body.get("lottery_type") or "lotto_max"
    if not valid_lottery_type(lottery_type):
        await db.close()
        raise HTTPException(400, "Unknown lottery type")
    if not draw_date:
        await db.close()
        raise HTTPException(400, "Draw date is required")
    suggestion = await suggest_new_round(lottery_type, draw_date=draw_date)
    if suggestion.get("error"):
        await db.close()
        raise HTTPException(400, "Invalid draw date for this lottery")
    jackpot = suggestion.get("jackpot") or 0
    seq_cur = await db.execute(
        "SELECT COALESCE(MAX(group_seq), 0) + 1 AS seq FROM rounds WHERE group_id=?", (gid,)
    )
    group_seq = (await seq_cur.fetchone())["seq"]
    cur = await db.execute(
        """INSERT INTO rounds
           (status, draw_date, jackpot, tickets_target, price_per_share, lottery_type, group_id, group_seq)
           VALUES ('open', ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (draw_date, jackpot, tickets_target, price_per_share, lottery_type, gid, group_seq),
    )
    round_id = cur.lastrowid
    await db.commit()

    await _auto_join_round(db, round_id, price_per_share, group_id=gid)

    applied_free = await apply_pending_free_tickets(
        db,
        round_id=round_id,
        group_id=gid,
        lottery_type=lottery_type,
        price_per_share=float(price_per_share),
    )
    if applied_free > 0:
        await db.commit()
        cur = await db.execute(
            """SELECT p.user_id, p.free_ticket_shares
               FROM participations p WHERE p.round_id = ? AND p.free_ticket_shares > 0""",
            (round_id,),
        )
        for row in await cur.fetchall():
            shares = row["free_ticket_shares"]
            await _notify(row["user_id"], render_notif(
                "free_tickets", group_id=gid, seq=group_seq, shares=shares,
                share_s="" if shares == 1 else "s", game=lottery_label(lottery_type)))

    jackpot_line = f"🏆 Jackpot: <b>${jackpot/1_000_000:.0f}M</b>\n" if jackpot else ""
    draw_line = f"📅 Draw: <b>{draw_date}</b>\n" if draw_date else ""
    target_str = f"target {tickets_target} tickets" if tickets_target else "no ticket limit"
    await _notify_all(db,
        render_notif("new_round", group_id=gid, seq=group_seq, jackpot_line=jackpot_line,
                     draw_line=draw_line, price=f"{price_per_share:.0f}", target=target_str),
        setting_col="notif_new_round",
        group_id=gid,
    )

    await db.close()
    return {"ok": True, "round_id": round_id, "round_no": group_seq}


@app.post("/api/admin/round/delete")
async def admin_delete_round(request: Request):
    """Delete a round that nobody has joined yet (no participations)."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    cur = await db.execute("SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, gid))
    round_ = await cur.fetchone()
    if not round_:
        await db.close()
        raise HTTPException(404, "Round not found")
    if round_["status"] not in ("open", "closed"):
        await db.close()
        raise HTTPException(400, "Only an open round can be deleted")
    cnt = await db.execute(
        "SELECT COUNT(*) AS n FROM participations WHERE round_id=?", (round_id,)
    )
    n = int((await cnt.fetchone())["n"] or 0)
    if n > 0:
        await db.close()
        raise HTTPException(400, "Cannot delete — this round already has participants")
    await db.execute("DELETE FROM rounds WHERE id=?", (round_id,))
    await db.commit()
    await db.close()
    return {"ok": True, "round_id": round_id}


@app.post("/api/admin/round/jackpot")
async def admin_round_jackpot(request: Request):
    """Set or fetch the estimated jackpot for a round."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    if not round_id:
        await db.close()
        raise HTTPException(400, "round_id required")
    cur = await db.execute(
        "SELECT * FROM rounds WHERE id=? AND group_id=?",
        (int(round_id), gid),
    )
    round_ = await cur.fetchone()
    if not round_:
        await db.close()
        raise HTTPException(404, "Round not found")
    rd = dict(round_)
    if rd.get("status") not in ("open", "closed"):
        await db.close()
        raise HTTPException(400, "Jackpot cannot be updated for this round")

    if body.get("fetch"):
        jackpot = await _try_fetch_round_jackpot(rd)
        if not jackpot:
            await db.close()
            raise HTTPException(404, "Jackpot not published on lotto site yet")
    else:
        try:
            jackpot = int(body.get("jackpot") or 0)
        except (TypeError, ValueError):
            jackpot = 0
        if jackpot < 1:
            await db.close()
            raise HTTPException(400, "Enter a valid jackpot amount (CAD)")

    await db.execute("UPDATE rounds SET jackpot=? WHERE id=?", (jackpot, rd["id"]))
    await db.commit()
    await db.close()
    return {"ok": True, "jackpot": jackpot}


@app.post("/api/admin/round/close")
async def admin_close_round(request: Request):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    round_id = body.get("round_id")
    if round_id:
        cur = await db.execute(
            "SELECT * FROM rounds WHERE id=? AND status='open' AND group_id=?",
            (int(round_id), gid),
        )
    else:
        cur = await db.execute(
            f"SELECT * FROM rounds WHERE status='open' AND group_id=? ORDER BY {_OPEN_ROUNDS_ORDER} LIMIT 1",
            (gid,),
        )
    round_ = await cur.fetchone()
    if round_ is None:
        raise HTTPException(400, "No open round")
    await db.execute(
        "UPDATE rounds SET status='closed', closed_at=datetime('now') WHERE id=?",
        (round_["id"],),
    )
    await db.commit()
    await _notify_round_closed(db, round_["id"])
    await db.close()
    return {"ok": True, "round_id": round_["id"]}


@app.post("/api/admin/round/ticket")
async def admin_save_round_ticket(request: Request):
    """Save one scanned physical ticket (image + rows) before finalizing the round."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    ticket_index = int(body.get("ticket_index", 0))
    numbers = body.get("rows") or body.get("numbers", [])
    image_data = body.get("image_b64", "")

    if ticket_index < 0:
        await db.close()
        raise HTTPException(400, "Invalid ticket_index")

    cur = await db.execute("SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, gid))
    round_ = await cur.fetchone()
    if not round_:
        await db.close()
        raise HTTPException(400, "Round not found")

    lottery_type = round_.get("lottery_type") or "lotto_max"
    rows = normalize_ticket_rows(numbers, lottery_type)
    if not rows:
        await db.close()
        raise HTTPException(400, "No ticket numbers provided")

    image_url = None
    if image_data:
        media_type = "image/jpeg"
        if image_data.startswith("data:"):
            header, image_data = image_data.split(",", 1)
            if "png" in header:
                media_type = "image/png"
            elif "webp" in header:
                media_type = "image/webp"
        img_bytes = base64.b64decode(image_data)
        if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
            try:
                image_url = await _upload_ticket_to_storage(
                    round_["id"], img_bytes, media_type, ticket_index
                )
            except Exception as exc:
                log.warning("Storage upload failed for ticket %s: %s", ticket_index, exc)
        if not image_url:
            image_url = f"data:{media_type};base64,{image_data}"

    tickets = parse_round_tickets(round_.get("round_tickets"), lottery_type)
    entry = {"image": image_url, "rows": rows}

    # Duplicate guard: reject identical numbers already saved at another index.
    def _sig(rs):
        return "|".join(sorted("-".join(str(n) for n in sorted(r)) for r in rs if r))
    new_sig = _sig(rows)
    if new_sig:
        for j, t in enumerate(tickets):
            if j != ticket_index and t.get("rows") and _sig(t["rows"]) == new_sig:
                await db.close()
                raise HTTPException(409, "Duplicate ticket — these numbers were already saved")

    if ticket_index < len(tickets):
        tickets[ticket_index] = entry
    elif ticket_index == len(tickets):
        tickets.append(entry)
    else:
        await db.close()
        raise HTTPException(400, "Save tickets in order (missing earlier ticket)")

    first_image = tickets[0].get("image") if tickets else None
    await _save_round_tickets_json(db, round_["id"], tickets)
    if first_image:
        await db.execute(
            "UPDATE rounds SET ticket_image=? WHERE id=?",
            (first_image, round_["id"]),
        )
    draw_date = body.get("draw_date")
    if draw_date and not round_.get("draw_date"):
        await db.execute("UPDATE rounds SET draw_date=? WHERE id=?", (draw_date, round_["id"]))
    await db.commit()

    required = await _round_tickets_required(db, round_)
    await db.close()
    all_rows = merge_round_ticket_rows(tickets)
    return {
        "ok": True,
        "round_id": round_["id"],
        "ticket_index": ticket_index,
        "tickets_uploaded": count_tickets(all_rows, lottery_type),
        "tickets_required": required,
        "rows_per_ticket": rows_per_ticket(lottery_type),
        "rows": rows,
    }


# Keep strong references to fire-and-forget tasks so they aren't GC'd mid-run.
_bg_tasks: set = set()


def _spawn_bg(coro):
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


def _round_email_html(*, round_id, name, group_name, game_label, draw_date, nums_str,
                      shares, stake_amount, share_pct, pool, ticket_count):
    """Simple, themed HTML body for the per-participant round email."""
    grp = html.escape(group_name)
    pct_line = f"{share_pct}% of ${pool:.2f}" if share_pct is not None else "—"
    ticket_note = (
        f"Your {ticket_count} ticket photo{'s' if ticket_count != 1 else ''} "
        "and your signed round agreement are attached to this email."
        if ticket_count else
        "Your signed round agreement is attached to this email."
    )
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#17212b">
  <div style="background:#17212b;color:#fff;padding:22px 24px;border-radius:14px 14px 0 0">
    <div style="font-size:20px;font-weight:800">🎟️ {grp}</div>
    <div style="font-size:13px;opacity:.8;margin-top:4px">Round #{round_id} — ticket purchased</div>
  </div>
  <div style="border:1px solid #e6ebf1;border-top:none;border-radius:0 0 14px 14px;padding:22px 24px">
    <p style="font-size:15px;margin:0 0 14px">Hi {html.escape(name)},</p>
    <p style="font-size:14px;line-height:1.6;margin:0 0 16px;color:#3a4a5a">
      The official ticket for your pool has been purchased. Here are your round details.
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px">
      <tr><td style="padding:6px 0;color:#5e7286">Game</td><td style="padding:6px 0;text-align:right;font-weight:600">{html.escape(game_label)}</td></tr>
      <tr><td style="padding:6px 0;color:#5e7286">Draw date</td><td style="padding:6px 0;text-align:right;font-weight:600">{html.escape(str(draw_date or 'TBD'))}</td></tr>
      <tr><td style="padding:6px 0;color:#5e7286">Your shares</td><td style="padding:6px 0;text-align:right;font-weight:600">{shares}</td></tr>
      <tr><td style="padding:6px 0;color:#5e7286">Your stake</td><td style="padding:6px 0;text-align:right;font-weight:600">${stake_amount:.2f} CAD</td></tr>
      <tr><td style="padding:6px 0;color:#5e7286">Pool share</td><td style="padding:6px 0;text-align:right;font-weight:600">{pct_line}</td></tr>
    </table>
    <div style="background:#f3f6f9;border-radius:10px;padding:14px 16px;margin:18px 0;font-size:14px">
      <div style="color:#5e7286;font-size:12px;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px">Ticket numbers</div>
      <div style="font-weight:700;font-size:15px;color:#17212b">{nums_str}</div>
    </div>
    <p style="font-size:13px;line-height:1.6;color:#5e7286;margin:0">{ticket_note}</p>
    <p style="font-size:12px;color:#8596a8;margin:18px 0 0">Good luck! 🍀 — {grp}</p>
  </div>
</div>"""


async def _email_round_documents(*, round_id, group_name, lottery_type, draw_date,
                                 closed_at, pool, trustee, participants, ticket_images,
                                 nums_str, participants_count=None):
    """Email each participant their round agreement PDF + ticket photos (Resend)."""
    if not email_enabled():
        return
    game_label = lottery_label(lottery_type)
    plain_nums = re.sub(r"<[^>]+>", "", nums_str or "").strip() or None
    # Ticket photos are shared across all participants — build the attachments once.
    img_atts = []
    for i, img in enumerate(ticket_images[:10], start=1):
        att = image_attachment(f"round-{round_id}-ticket-{i}.jpg", img)
        if att:
            img_atts.append(att)
    sent = 0
    for p in participants:
        email = (p.get("email") or "").strip()
        if not email:
            continue
        name = p.get("name") or "there"
        shares = p.get("shares") or 1
        stake = float(p.get("amount") or 0)
        share_pct = round(stake / pool * 100, 1) if pool else None
        try:
            body = build_round_agreement(
                round_id=round_id, lottery_type=lottery_type, draw_date=draw_date,
                beneficiary_name=name, shares=shares, stake_amount=stake,
                pool_amount=pool, share_pct=share_pct, closed_at=closed_at, trustee=trustee,
                participants_count=participants_count, ticket_numbers=plain_nums,
            )
            pdf = build_agreement_pdf(
                title=f"Round #{round_id} Draw Agreement",
                subtitle=f"Addendum · {game_label} · Draw {draw_date or 'TBD'}",
                body=body,
                highlights=[
                    ("Beneficiary", name),
                    ("Shares", str(shares)),
                    ("Stake", f"${stake:.2f} CAD"),
                    ("Pool share", f"{share_pct}% of ${pool:.2f}" if share_pct is not None else "—"),
                ],
            )
            attachments = [pdf_attachment(f"round-{round_id}-agreement.pdf", pdf)] + img_atts
            html_body = _round_email_html(
                round_id=round_id, name=name, group_name=group_name, game_label=game_label,
                draw_date=draw_date, nums_str=nums_str, shares=shares, stake_amount=stake,
                share_pct=share_pct, pool=pool, ticket_count=len(img_atts),
            )
            ok = await send_email(
                email,
                f"🎟️ {group_name} — Round #{round_id} ticket & agreement",
                html_body,
                attachments=attachments,
            )
            if ok:
                sent += 1
        except Exception as e:
            log.warning("round email failed for %s: %s", email, e)
    if sent:
        log.info("round #%s: emailed agreement+ticket to %s participant(s)", round_id, sent)


@app.post("/api/admin/round/upload-ticket")
async def admin_upload_ticket(request: Request):
    """Finalize ticket upload for a round (sets status to 'uploaded')."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    numbers = body.get("numbers")

    if round_id:
        cur = await db.execute("SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, gid))
    else:
        cur = await db.execute(
            "SELECT * FROM rounds WHERE group_id=? AND status IN ('open','closed') ORDER BY id DESC LIMIT 1",
            (gid,),
        )
    round_ = await cur.fetchone()
    if not round_:
        raise HTTPException(400, "No suitable round found")

    lottery_type = round_.get("lottery_type") or "lotto_max"
    required = await _round_tickets_required(db, round_)

    if numbers is not None and numbers != []:
        rows = normalize_ticket_rows(numbers, lottery_type)
    else:
        saved = parse_round_tickets(round_.get("round_tickets"), lottery_type)
        rows = merge_round_ticket_rows(saved)
        uploaded = count_tickets(rows, lottery_type)
        if uploaded < required:
            await db.close()
            raise HTTPException(
                400,
                f"Scan {required - uploaded} more ticket(s) — "
                f"{uploaded} of {required} uploaded",
            )

    if not validate_ticket_rows(rows, lottery_type):
        await db.close()
        raise HTTPException(400, "Enter all ticket numbers for every line on the ticket")

    await db.execute(
        "UPDATE rounds SET ticket_numbers=?, status='uploaded' WHERE id=?",
        (json.dumps(rows), round_["id"])
    )
    await db.commit()

    # Notify participants: ticket purchased
    draw_date_str = round_["draw_date"] or "TBD"
    nums_str = format_ticket_numbers_message(rows, lottery_type)
    cur = await db.execute(
        "SELECT p.user_id FROM participations p WHERE p.round_id=?", (round_["id"],)
    )
    participant_ids = [r["user_id"] for r in await cur.fetchall()]
    for uid in participant_ids:
        setting = await db.execute(
            "SELECT notif_ticket, notif_reminder FROM user_settings WHERE user_id=?", (uid,)
        )
        s = await setting.fetchone()
        notif_ticket   = s["notif_ticket"]   if s else 1
        notif_reminder = s["notif_reminder"] if s else 1
        msg_parts = []
        if notif_ticket:
            msg_parts.append(render_notif("ticket_purchased", group_id=round_.get("group_id"),
                                          rid=round_["id"], numbers=nums_str))
        if notif_reminder:
            msg_parts.append(render_notif("draw_reminder", group_id=round_.get("group_id"),
                                          draw=draw_date_str))
        if msg_parts:
            await _notify(uid, "\n".join(msg_parts))

    # Email the round agreement + ticket photos to participants (Resend).
    if email_enabled():
        pool = round_.get("pool") or 0
        cur = await db.execute(
            """SELECT p.user_id, p.amount, p.shares, u.full_name, u.username,
                      COALESCE(NULLIF(u.auth_email,''), NULLIF(u.email,'')) AS email
               FROM participations p JOIN users u ON u.telegram_id = p.user_id
               WHERE p.round_id=?""",
            (round_["id"],),
        )
        email_parts = []
        for r in await cur.fetchall():
            if not (r["email"] or "").strip():
                continue
            email_parts.append({
                "user_id": r["user_id"], "email": r["email"],
                "name": r["full_name"] or r["username"] or f"User {r['user_id']}",
                "shares": r["shares"] or 1, "amount": r["amount"],
            })
        if email_parts:
            saved_tk = parse_round_tickets(round_.get("round_tickets"), lottery_type)
            ticket_images = [t["image"] for t in saved_tk if t.get("image")]
            if not ticket_images and round_.get("ticket_image"):
                ticket_images = [round_["ticket_image"]]
            trustee = await _trustee_dict_for_user(db, user)
            _spawn_bg(_email_round_documents(
                round_id=round_["id"], group_name=group["name"], lottery_type=lottery_type,
                draw_date=round_.get("draw_date"), closed_at=round_.get("closed_at"),
                pool=pool, trustee=trustee, participants=email_parts,
                ticket_images=ticket_images, nums_str=nums_str,
                participants_count=len(participant_ids),
            ))

    await db.close()
    return {"ok": True, "round_id": round_["id"]}


@app.post("/api/admin/round/scan-ticket")
async def admin_scan_ticket(request: Request):
    """Upload ticket image; optional client OCR rows, else Claude Vision fallback."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    image_data = body.get("image_b64", "")
    client_rows = body.get("rows")

    if not image_data:
        await db.close()
        raise HTTPException(400, "No image provided")

    media_type = "image/jpeg"
    raw_b64 = image_data
    if image_data.startswith("data:"):
        header, raw_b64 = image_data.split(",", 1)
        if "png" in header:
            media_type = "image/png"
        elif "webp" in header:
            media_type = "image/webp"

    if round_id:
        cur = await db.execute("SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, gid))
    else:
        cur = await db.execute(
            "SELECT * FROM rounds WHERE group_id=? ORDER BY id DESC LIMIT 1", (gid,)
        )
    round_ = await cur.fetchone()
    if not round_:
        await db.close()
        raise HTTPException(400, "No round found")

    lottery_type = round_.get("lottery_type") or "lotto_max"
    ticket_index = int(body.get("ticket_index", 0))
    draw_date = body.get("draw_date")
    result = {}

    if client_rows:
        rows = normalize_ticket_rows(client_rows, lottery_type)
    elif config.ANTHROPIC_API_KEY:
        scan_prompt = build_scan_prompt(lottery_type)
        client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
        try:
            msg = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": raw_b64},
                        },
                        {"type": "text", "text": scan_prompt},
                    ],
                }],
            )
            raw = msg.content[0].text.strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            result = json.loads(raw)
        except json.JSONDecodeError:
            await db.close()
            raise HTTPException(422, "Could not read ticket data — try a clearer photo")
        except Exception as e:
            log.exception("Claude scan error: %s", e)
            await db.close()
            raise HTTPException(422, f"Scan error: {e}")
        raw_rows = result.get("rows")
        if not isinstance(raw_rows, list) and isinstance(result.get("numbers"), list):
            raw_rows = [result.get("numbers")]
        rows = normalize_ticket_rows(raw_rows or [], lottery_type)
        draw_date = draw_date or result.get("draw_date")
    else:
        await db.close()
        raise HTTPException(400, "No OCR rows — scan on device or set ANTHROPIC_API_KEY")

    # Preview scan: just return the read numbers; the trustee reviews them and the
    # canonical image+rows are persisted later via /api/admin/round/ticket. This
    # keeps scanning fast and avoids re-uploading the image on every retake.
    if body.get("preview"):
        await db.close()
        return {
            "ok": True,
            "round_id": round_["id"],
            "draw_date": draw_date or result.get("draw_date"),
            "rows": rows,
            "numbers": rows[0] if rows else [],
            "image_url": None,
        }

    img_bytes = base64.b64decode(raw_b64)
    storage_url = None
    if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
        try:
            storage_url = await _upload_ticket_to_storage(
                round_["id"], img_bytes, media_type, ticket_index
            )
            log.info("Ticket uploaded to Storage: %s", storage_url)
        except Exception as exc:
            log.warning("Storage upload failed: %s", exc)
    if storage_url:
        if ticket_index == 0:
            await db.execute(
                "UPDATE rounds SET ticket_image=? WHERE id=?", (storage_url, round_["id"])
            )
    else:
        await db.execute(
            "UPDATE rounds SET ticket_image=? WHERE id=?",
            (f"data:{media_type};base64,{raw_b64}", round_["id"]),
        )
    if draw_date and not round_.get("draw_date"):
        await db.execute("UPDATE rounds SET draw_date=? WHERE id=?", (draw_date, round_["id"]))
    await db.commit()
    await db.close()

    return {
        "ok": True,
        "round_id": round_["id"],
        "draw_date": draw_date or result.get("draw_date"),
        "rows": rows,
        "numbers": rows[0] if rows else [],
        "image_url": storage_url,
    }


@app.get("/api/round/{round_id}/ticket-image")
async def round_ticket_image(request: Request, round_id: int):
    """Serve the stored ticket image for any authenticated user."""
    user, db = await _auth(request)
    cur = await db.execute("SELECT ticket_image FROM rounds WHERE id=?", (round_id,))
    row = await cur.fetchone()
    await db.close()
    if not row or not row["ticket_image"]:
        raise HTTPException(404, "No ticket image for this round")
    val = row["ticket_image"]
    if val.startswith("http"):
        return RedirectResponse(url=val)
    try:
        img_bytes = base64.b64decode(val)
    except Exception:
        raise HTTPException(500, "Invalid image data")
    return Response(content=img_bytes, media_type="image/jpeg")


def _build_ticket_breakdown(lines, lottery_type, winning_main, bonus, ticket_inputs=None):
    """Group the pool's lines into physical tickets with per-line match + per-ticket
    prize/free info. `ticket_inputs` is an optional list aligned to the tickets:
    [{"prize": float, "free": int}, ...]."""
    matched = match_lines(lottery_type, winning_main, bonus, lines)
    line_infos = matched["lines"]
    groups = group_rows_into_tickets(line_infos, lottery_type)
    inputs = ticket_inputs or []
    out = []
    for i, grp in enumerate(groups):
        inp = inputs[i] if i < len(inputs) else {}
        try:
            prize = round(float(inp.get("prize") or 0), 2)
        except (TypeError, ValueError):
            prize = 0.0
        try:
            free = int(inp.get("free") or 0)
        except (TypeError, ValueError):
            free = 0
        best = max((li["main_matches"] for li in grp), default=0)
        best_bonus = any(li["bonus_matched"] for li in grp)
        any_line_win = any(li["win"] for li in grp)
        # Free tickets count as a win, per group rules.
        won = any_line_win or prize > 0 or free > 0
        out.append({
            "lines": grp,
            "best_main": best,
            "best_bonus": best_bonus,
            "best_label": f"{best}/{matched['main_count']}" + (" + bonus" if best_bonus else ""),
            "line_win": any_line_win,
            "won": won,
            "prize": prize,
            "free": free,
        })
    return out


def _ticket_breakdown_for_round(rd: dict, all_rows=None):
    """Per-ticket lines + win/prize breakdown for display. Uses the stored
    `ticket_results` once a round is drawn, else derives lines (no win marks)."""
    stored = rd.get("ticket_results")
    if stored:
        try:
            return json.loads(stored) if isinstance(stored, str) else stored
        except (ValueError, TypeError):
            pass
    lt = rd.get("lottery_type")
    lines = parse_ticket_numbers(rd.get("ticket_numbers")) or (all_rows or [])
    if not lines:
        return None
    wn = []
    try:
        wn = json.loads(rd["winning_numbers"]) if rd.get("winning_numbers") else []
    except (ValueError, TypeError):
        wn = []
    return _build_ticket_breakdown(lines, lt, wn, rd.get("bonus_number"))


@app.post("/api/admin/round/results")
async def admin_enter_results(request: Request):
    """Trustee enters winning numbers and a prize per ticket (summed to total)."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    winning_numbers = body.get("winning_numbers", [])
    bonus_number = body.get("bonus_number")
    # New per-ticket model: `tickets` = [{prize, free}, ...] summed to the total.
    # Falls back to whole-round total_prize / free_tickets for older clients.
    ticket_inputs = body.get("tickets")
    if isinstance(ticket_inputs, list) and ticket_inputs:
        total_prize = round(sum(float(t.get("prize") or 0) for t in ticket_inputs), 2)
        free_tickets = sum(int(t.get("free") or 0) for t in ticket_inputs)
    else:
        ticket_inputs = None
        total_prize = float(body.get("total_prize", 0))
        free_tickets = int(body.get("free_tickets") or 0)

    if round_id:
        cur = await db.execute("SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, gid))
    else:
        cur = await db.execute(
            "SELECT * FROM rounds WHERE group_id=? AND status='uploaded' ORDER BY id DESC LIMIT 1",
            (gid,),
        )
    round_ = await cur.fetchone()
    if not round_:
        raise HTTPException(400, "No uploaded round found")

    cur = await db.execute("SELECT * FROM participations WHERE round_id=?", (round_["id"],))
    parts = [dict(p) for p in await cur.fetchall()]
    pool = round_["pool"] or sum(p["amount"] for p in parts)

    if not winning_numbers:
        await db.close()
        raise HTTPException(400, "Winning numbers are required")
    if total_prize < 0 or free_tickets < 0:
        await db.close()
        raise HTTPException(400, "Prize amounts cannot be negative")
    if total_prize <= 0 and free_tickets <= 0:
        await db.close()
        raise HTTPException(400, "Enter a cash prize and/or free tickets won")

    mode = normalize_free_ticket_mode(group.get("free_ticket_mode"))
    lottery_type = round_.get("lottery_type") or "lotto_max"
    free_ticket_allocation: dict[int, int] = {}
    free_ticket_cash_total = 0.0

    if free_tickets > 0 and mode == "cash_credit":
        free_ticket_cash_total = free_ticket_cash_value(lottery_type, free_tickets)
        trustee_id = group["trustee_user_id"]
        cur = await db.execute("SELECT credit FROM users WHERE telegram_id=?", (trustee_id,))
        trustee = await cur.fetchone()
        trustee_credit = float((trustee or {}).get("credit") or 0)
        if trustee_credit < free_ticket_cash_total:
            await db.close()
            raise HTTPException(
                400,
                f"Your trustee credit (${trustee_credit:.2f}) is less than the free-ticket "
                f"value (${free_ticket_cash_total:.2f}). Top up or choose “Next round” mode.",
            )
        await db.execute(
            "UPDATE users SET credit=credit-? WHERE telegram_id=?",
            (free_ticket_cash_total, trustee_id),
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
            (
                trustee_id,
                "free_ticket",
                -free_ticket_cash_total,
                f"Free tickets Round #{round_['id']}",
                gid,
            ),
        )
    elif free_tickets > 0:
        free_ticket_allocation = distribute_integer_shares(free_tickets, parts, pool)

    prize_by_user: dict[int, float] = {}
    for p in parts:
        share = p["amount"] / pool if pool else 0
        prize = round(share * total_prize, 2) if total_prize > 0 and pool > 0 else 0.0
        if free_tickets > 0 and mode == "cash_credit" and pool > 0:
            prize = round(prize + share * free_ticket_cash_total, 2)
        prize_by_user[p["user_id"]] = prize
        ft_awarded = free_ticket_allocation.get(p["user_id"], 0) if mode == "next_round" else 0
        await db.execute(
            """UPDATE participations SET prize=?, free_tickets_awarded=?
               WHERE round_id=? AND user_id=?""",
            (prize, ft_awarded, round_["id"], p["user_id"]),
        )
        if prize > 0:
            await db.execute(
                "UPDATE users SET credit=credit+? WHERE telegram_id=?", (prize, p["user_id"])
            )
            await db.execute(
                "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
                (p["user_id"], "win", prize, f"Prize Round #{round_['id']}", gid),
            )

    # Per-ticket match + prize breakdown (for participant "see winning tickets" view).
    ticket_lines = parse_ticket_numbers(round_.get("ticket_numbers"))
    ticket_breakdown = _build_ticket_breakdown(
        ticket_lines, lottery_type, winning_numbers, bonus_number, ticket_inputs
    )
    await db.execute(
        """UPDATE rounds SET status='drawn', winning_numbers=?, bonus_number=?,
           drawn_at=datetime('now'), free_tickets_won=?, ticket_results=? WHERE id=?""",
        (json.dumps(winning_numbers), bonus_number, free_tickets,
         json.dumps(ticket_breakdown), round_["id"]),
    )
    await db.commit()

    win_str = "  ".join(f"<b>{n}</b>" for n in winning_numbers)
    if bonus_number:
        win_str += f"  +<b>{bonus_number}</b> (bonus)"
    game_label = lottery_label(lottery_type)
    for p in parts:
        setting = await db.execute(
            "SELECT notif_results FROM user_settings WHERE user_id=?", (p["user_id"],)
        )
        s = await setting.fetchone()
        if s and not s["notif_results"]:
            continue
        prize = prize_by_user.get(p["user_id"], 0)
        share_pct = round(p["amount"] / pool * 100, 1) if pool else 0
        ft = free_ticket_allocation.get(p["user_id"], 0)
        if prize > 0 or ft > 0:
            prize_line = f"💵 Cash prize: <b>${prize:.2f}</b> (your {share_pct}% share)\n" if prize > 0 else ""
            ft_line = f"🎟️ Free tickets: <b>{ft}</b> — auto-applied in the next {game_label} round\n" if ft > 0 else ""
            credited_line = "✅ Credited straight to your balance! 💰" if prize > 0 else ""
            msg = render_notif("you_won", group_id=gid, rid=round_["id"], prize_line=prize_line,
                               ft_line=ft_line, numbers=win_str, credited_line=credited_line)
        else:
            msg = render_notif("results_no_prize", group_id=gid, rid=round_["id"], numbers=win_str,
                               stake=f"{p['amount']:.2f}", pct=share_pct)
        await _notify(p["user_id"], msg)

    await db.close()
    return {
        "ok": True,
        "total_prize": total_prize,
        "free_tickets": free_tickets,
        "free_ticket_mode": mode,
        "distributed": len(parts),
    }


@app.post("/api/admin/round/draw")
async def admin_draw(request: Request):
    """
    LEGACY / DEPRECATED: Old random winner-takes-all draw.
    New flow: use /api/admin/round/upload-ticket then /api/admin/round/results.
    Kept for backward compatibility only — calls results with total_prize=0.
    """
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    cur = await db.execute(
        "SELECT * FROM rounds WHERE group_id=? AND status IN ('closed','uploaded') ORDER BY id DESC LIMIT 1",
        (gid,),
    )
    round_ = await cur.fetchone()
    if round_ is None:
        raise HTTPException(400, "No closed round to draw from")
    cur = await db.execute("SELECT * FROM participations WHERE round_id=?", (round_["id"],))
    parts = await cur.fetchall()
    if not parts:
        raise HTTPException(400, "No participants in this round")
    pool_val = round_["pool"] or sum(p["amount"] for p in parts)
    weighted = []
    for p in parts:
        weighted.extend([p["user_id"]] * max(1, int(p["amount"] * 100)))
    winner_id = random.choice(weighted)
    cur = await db.execute(
        "SELECT full_name, username FROM users WHERE telegram_id=?", (winner_id,)
    )
    w = await cur.fetchone()
    winner_name = (w["full_name"] or w["username"]) if w else str(winner_id)
    winner_part = next((p for p in parts if p["user_id"] == winner_id), None)
    winner_pct  = round(winner_part["amount"] / pool_val * 100, 1) if winner_part and pool_val else 0
    ticket_ref  = f"TKT-{round_['id']:04d}-{winner_id}"
    await db.execute(
        "UPDATE rounds SET status='drawn', winner_id=?, ticket_ref=?, drawn_at=datetime('now') WHERE id=?",
        (winner_id, ticket_ref, round_["id"])
    )
    await db.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (pool_val, winner_id))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (winner_id, "win", pool_val, f"Won round #{round_['id']}"),
    )
    await db.commit()
    await db.close()
    return {"ok": True, "winner_name": winner_name, "pool": pool_val,
            "winner_pct": winner_pct, "round_id": round_["id"]}


@app.get("/api/admin/deposits")
async def admin_deposits(request: Request):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    cur = await db.execute(
        "SELECT dr.*, u.full_name, u.username FROM deposit_requests dr "
        "JOIN users u ON u.telegram_id=dr.user_id "
        "WHERE dr.status='pending' AND dr.group_id=? ORDER BY dr.created_at",
        (gid,),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"deposits": rows, "imap_configured": bool(config.IMAP_HOST)}


@app.post("/api/admin/deposits/{req_id}")
async def admin_resolve_deposit(
    req_id: int, request: Request
):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    body = await request.json()
    action = body.get("action")
    cur = await db.execute(
        "SELECT * FROM deposit_requests WHERE id=? AND group_id=?", (req_id, gid)
    )
    dep = await cur.fetchone()
    if dep is None:
        raise HTTPException(404, "Deposit request not found")
    if dep["status"] != "pending":
        raise HTTPException(400, "Already resolved")
    if action == "approve":
        # The trustee may adjust the amount before approving (e.g. the e-transfer
        # actually received differs from what the member requested).
        amount = dep["amount"]
        if body.get("amount") is not None:
            try:
                amount = round(float(body["amount"]), 2)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid amount")
            if amount <= 0:
                raise HTTPException(400, "Amount must be positive")
        note = f"Approved deposit #{req_id}"
        if amount != dep["amount"]:
            note += f" (adjusted from ${dep['amount']:.2f})"
        await db.execute(
            "UPDATE users SET credit=credit+? WHERE telegram_id=?", (amount, dep["user_id"])
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
            (dep["user_id"], "deposit", amount, note, gid),
        )
        await db.execute(
            "UPDATE deposit_requests SET status='approved', amount=?, resolved_at=datetime('now') WHERE id=?",
            (amount, req_id)
        )
    elif action == "reject":
        await db.execute(
            "UPDATE deposit_requests SET status='rejected', resolved_at=datetime('now') WHERE id=?",
            (req_id,)
        )
    else:
        raise HTTPException(400, "action must be approve or reject")
    await db.commit()
    await db.close()
    return {"ok": True}


@app.get("/api/admin/members")
async def admin_members(request: Request):
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    cur = await db.execute(
        """SELECT u.* FROM users u
           JOIN group_members gm ON gm.user_id = u.telegram_id
           WHERE gm.group_id = ?
           ORDER BY gm.joined_at, u.created_at""",
        (gid,),
    )
    rows = []
    for r in await cur.fetchall():
        d = dict(r)
        d["is_group_trustee"] = d["telegram_id"] == group["trustee_user_id"]
        rows.append(d)
    await db.close()
    return {"members": rows}


@app.post("/api/admin/etransfer/check")
async def admin_check_etransfer(request: Request):
    """Manually trigger IMAP check to auto-approve matched e-transfer deposits."""
    user, db, _group = await _require_group_trustee(request)
    if not config.IMAP_HOST:
        await db.close()
        raise HTTPException(400, "IMAP not configured (set IMAP_HOST, IMAP_USER, IMAP_PASS)")
    result = await _check_etransfer_emails(db)
    await db.close()
    return result


# ---------------------------------------------------------------------------
# Platform admin
# ---------------------------------------------------------------------------

@app.get("/api/platform/overview")
async def platform_overview(request: Request):
    user, db = await _require_platform_admin(request)
    counts = {}
    for key, sql in [
        ("users", "SELECT COUNT(*) AS c FROM users"),
        ("groups", "SELECT COUNT(*) AS c FROM groups"),
        ("open_rounds", "SELECT COUNT(*) AS c FROM rounds WHERE status='open'"),
        ("pending_applications", "SELECT COUNT(*) AS c FROM trustee_applications WHERE status='pending'"),
        ("pending_deposits", "SELECT COUNT(*) AS c FROM deposit_requests WHERE status='pending'"),
    ]:
        cur = await db.execute(sql)
        row = await cur.fetchone()
        counts[key] = int(row["c"]) if row else 0
    await db.close()
    return counts


@app.get("/api/platform/groups")
async def platform_groups(request: Request):
    user, db = await _require_platform_admin(request)
    cur = await db.execute("""
        SELECT g.*, u.full_name AS trustee_name, u.username AS trustee_username,
               u.photo_url AS trustee_photo_url,
               (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id) AS member_count
        FROM groups g
        JOIN users u ON u.telegram_id = g.trustee_user_id
        ORDER BY g.id DESC
    """)
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"groups": rows}


@app.get("/api/platform/groups/{group_id}")
async def platform_group_detail(request: Request, group_id: int):
    await _require_platform_admin(request)
    db = await get_db()
    cur = await db.execute("""
        SELECT g.*, u.full_name AS trustee_name, u.username AS trustee_username,
               u.photo_url AS trustee_photo_url, u.email AS trustee_email
        FROM groups g
        JOIN users u ON u.telegram_id = g.trustee_user_id
        WHERE g.id = ?
    """, (group_id,))
    group = await cur.fetchone()
    if not group:
        await db.close()
        raise HTTPException(404, "Group not found")
    cur = await db.execute("""
        SELECT telegram_id, username, full_name, credit, email, photo_url,
               is_platform_admin, created_at
        FROM users u
        JOIN group_members gm ON gm.user_id = u.telegram_id
        WHERE gm.group_id = ?
        ORDER BY
          CASE WHEN u.telegram_id = ? THEN 0 ELSE 1 END,
          gm.joined_at, u.created_at
    """, (group_id, group["trustee_user_id"]))
    members = []
    for m in await cur.fetchall():
        row = dict(m)
        row["is_trustee"] = row["telegram_id"] == group["trustee_user_id"]
        members.append(row)
    cur = await db.execute(
        "SELECT COUNT(*) AS c FROM rounds WHERE group_id = ?", (group_id,)
   )
    rc = await cur.fetchone()
    rounds_count = int(rc["c"]) if rc else 0
    await db.close()
    g = dict(group)
    return {
        "group": g,
        "members": members,
        "rounds_count": rounds_count,
        "invite_link_slug": g["slug"],
    }


@app.get("/api/platform/users")
async def platform_users(
    request: Request,
    limit: int = 100,
    group_id: int | None = None,
):
    await _require_platform_admin(request)
    db = await get_db()
    sql = """
        SELECT u.*, g.name AS group_name, g.slug AS group_slug
        FROM users u
        LEFT JOIN groups g ON g.id = u.group_id
        WHERE 1=1
    """
    params: list = []
    if group_id is not None:
        sql += " AND u.group_id = ?"
        params.append(group_id)
    sql += " ORDER BY u.created_at DESC LIMIT ?"
    params.append(min(limit, 500))
    cur = await db.execute(sql, tuple(params))
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"users": rows}


@app.get("/api/platform/rounds")
async def platform_rounds(
    request: Request,
    group_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
):
    user, db = await _require_platform_admin(request)
    sql = """
        SELECT r.*, g.name AS group_name,
               (SELECT COUNT(*) FROM participations WHERE round_id = r.id) AS participants_count
        FROM rounds r
        JOIN groups g ON g.id = r.group_id
        WHERE 1=1
    """
    params: list = []
    if group_id is not None:
        sql += " AND r.group_id = ?"
        params.append(group_id)
    if status:
        sql += " AND r.status = ?"
        params.append(status)
    sql += " ORDER BY r.id DESC LIMIT ?"
    params.append(min(limit, 200))
    cur = await db.execute(sql, tuple(params))
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"rounds": rows}


@app.get("/api/platform/applications")
async def platform_applications(request: Request):
    user, db = await _require_platform_admin(request)
    await _maybe_auto_approve_applications(db)
    cur = await db.execute("""
        SELECT a.*, u.full_name, u.username
        FROM trustee_applications a
        JOIN users u ON u.telegram_id = a.applicant_user_id
        WHERE a.status = 'pending'
        ORDER BY a.created_at
    """)
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"applications": rows}


@app.post("/api/platform/applications/{app_id}/approve")
async def platform_approve_application(app_id: int, request: Request):
    admin, db = await _require_platform_admin(request)
    cur = await db.execute("SELECT * FROM trustee_applications WHERE id=?", (app_id,))
    app_row = await cur.fetchone()
    if not app_row or app_row["status"] != "pending":
        await db.close()
        raise HTTPException(404, "Pending application not found")
    result = await _approve_trustee_application(db, app_row, reviewed_by=admin["telegram_id"])
    await db.commit()
    await db.close()
    return {"ok": True, **result}


@app.post("/api/platform/applications/{app_id}/reject")
async def platform_reject_application(
    app_id: int, request: Request
):
    admin, db = await _require_platform_admin(request)
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    notes = body.get("review_notes") or body.get("notes")
    cur = await db.execute(
        """UPDATE trustee_applications SET status='rejected', reviewed_by=?,
           review_notes=?, reviewed_at=datetime('now')
           WHERE id=? AND status='pending'""",
        (admin["telegram_id"], notes, app_id),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


@app.patch("/api/platform/groups/{group_id}")
async def platform_patch_group(
    group_id: int, request: Request
):
    await _require_platform_admin(request)
    db = await get_db()
    cur = await db.execute("SELECT * FROM groups WHERE id=?", (group_id,))
    existing = await cur.fetchone()
    if not existing:
        await db.close()
        raise HTTPException(404, "Group not found")

    body = await request.json()
    name = body.get("name")
    if name is not None:
        name = str(name).strip()
        if not name:
            await db.close()
            raise HTTPException(400, "Group name cannot be empty")
        await db.execute("UPDATE groups SET name=? WHERE id=?", (name, group_id))

    status = body.get("status")
    if status is not None:
        if status not in ("active", "suspended"):
            await db.close()
            raise HTTPException(400, "status must be active or suspended")
        await db.execute("UPDATE groups SET status=? WHERE id=?", (status, group_id))

    if "etransfer_email" in body:
        email = (body.get("etransfer_email") or "").strip().lower() or None
        await db.execute(
            "UPDATE groups SET etransfer_email=? WHERE id=?", (email, group_id)
        )

    if "payment_methods" in body:
        pm = (body.get("payment_methods") or "both").lower()
        if pm not in VALID_PAYMENT_METHODS:
            await db.close()
            raise HTTPException(400, "payment_methods must be etransfer, card, or both")
        await db.execute(
            "UPDATE groups SET payment_methods=? WHERE id=?", (pm, group_id)
        )

    if "etransfer_min_amount" in body:
        try:
            min_amt = float(body["etransfer_min_amount"])
        except (TypeError, ValueError):
            await db.close()
            raise HTTPException(400, "Invalid etransfer_min_amount")
        if min_amt <= 0:
            await db.close()
            raise HTTPException(400, "etransfer_min_amount must be positive")
        await db.execute(
            "UPDATE groups SET etransfer_min_amount=? WHERE id=?", (min_amt, group_id)
        )

    if body.get("regenerate_slug") and name:
        base_slug = slugify(name)
        slug = base_slug
        n = 0
        while True:
            cur = await db.execute(
                "SELECT id FROM groups WHERE slug=? AND id<>?", (slug, group_id)
            )
            if not await cur.fetchone():
                break
            n += 1
            slug = f"{base_slug}-{n}"
        await db.execute("UPDATE groups SET slug=? WHERE id=?", (slug, group_id))

    new_trustee = body.get("trustee_user_id")
    if new_trustee is not None:
        new_trustee = int(new_trustee)
        cur = await db.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (new_trustee,))
        if not await cur.fetchone():
            await db.close()
            raise HTTPException(400, "Trustee user not found")
        await db.execute(
            "UPDATE groups SET trustee_user_id=? WHERE id=?", (new_trustee, group_id)
        )
        await db.execute(
            "UPDATE users SET group_id=? WHERE telegram_id=?", (group_id, new_trustee)
        )

    await db.commit()
    await db.close()
    detail = await platform_group_detail(request, group_id)
    return {"ok": True, **detail}


@app.post("/api/platform/groups")
async def platform_create_group(request: Request):
    """Super-admin creates a group directly, assigning a trustee + plan."""
    admin, db = await _require_platform_admin(request)
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        await db.close()
        raise HTTPException(400, "Group name required")
    trustee_id = body.get("trustee_user_id")
    if not trustee_id:
        await db.close()
        raise HTTPException(400, "A trustee user id is required")
    trustee_id = int(trustee_id)
    cur = await db.execute("SELECT telegram_id FROM users WHERE telegram_id=?", (trustee_id,))
    if not await cur.fetchone():
        await db.close()
        raise HTTPException(400, "Trustee user not found")
    plan = body.get("pricing_plan") or "subscription"
    if plan not in ("subscription", "prize_share"):
        plan = "subscription"
    base_slug = slugify(name)
    slug = base_slug
    n = 0
    while True:
        cur = await db.execute("SELECT id FROM groups WHERE slug=?", (slug,))
        if not await cur.fetchone():
            break
        n += 1
        slug = f"{base_slug}-{n}"
    join_code = generate_join_code()
    while True:
        cur = await db.execute("SELECT 1 FROM groups WHERE join_code=?", (join_code,))
        if not await cur.fetchone():
            break
        join_code = generate_join_code()
    cur = await db.execute(
        """INSERT INTO groups (name, slug, trustee_user_id, status, join_code, pricing_plan)
           VALUES (?,?,?, 'active', ?, ?) RETURNING id""",
        (name, slug, trustee_id, join_code, plan),
    )
    gid = cur.lastrowid
    await db.execute("UPDATE users SET group_id=? WHERE telegram_id=?", (gid, trustee_id))
    await add_group_member(db, gid, trustee_id, "trustee")
    await db.commit()
    await db.close()
    return {"ok": True, "group_id": gid, "slug": slug}


@app.delete("/api/platform/groups/{group_id}")
async def platform_delete_group(group_id: int, request: Request):
    """Delete a group. Blocked if any of its rounds have participants (money) —
    deactivate instead. Otherwise removes the group, its rounds and memberships."""
    admin, db = await _require_platform_admin(request)
    cur = await db.execute("SELECT id FROM groups WHERE id=?", (group_id,))
    if not await cur.fetchone():
        await db.close()
        raise HTTPException(404, "Group not found")
    cur = await db.execute(
        "SELECT COUNT(*) AS n FROM participations p JOIN rounds r ON r.id=p.round_id WHERE r.group_id=?",
        (group_id,),
    )
    if int((await cur.fetchone())["n"] or 0) > 0:
        await db.close()
        raise HTTPException(400, "Group has rounds with participants — deactivate it instead of deleting")
    await db.execute("DELETE FROM rounds WHERE group_id=?", (group_id,))
    await db.execute("UPDATE users SET group_id=NULL WHERE group_id=?", (group_id,))
    await db.execute("DELETE FROM group_members WHERE group_id=?", (group_id,))
    await db.execute("DELETE FROM groups WHERE id=?", (group_id,))
    await db.commit()
    await db.close()
    return {"ok": True}


@app.patch("/api/platform/rounds/{round_id}")
async def platform_patch_round(round_id: int, request: Request):
    """Super-admin edits a round (status, draw date, jackpot, winning numbers)."""
    admin, db = await _require_platform_admin(request)
    cur = await db.execute("SELECT id FROM rounds WHERE id=?", (round_id,))
    if not await cur.fetchone():
        await db.close()
        raise HTTPException(404, "Round not found")
    body = await request.json()
    if "status" in body:
        st = body.get("status")
        if st not in ("open", "closed", "uploaded", "drawn", "cancelled", "locked"):
            await db.close()
            raise HTTPException(400, "Invalid status")
        await db.execute("UPDATE rounds SET status=? WHERE id=?", (st, round_id))
    if "draw_date" in body:
        await db.execute("UPDATE rounds SET draw_date=? WHERE id=?", (body.get("draw_date") or None, round_id))
    if "jackpot" in body:
        try:
            await db.execute("UPDATE rounds SET jackpot=? WHERE id=?", (int(body.get("jackpot") or 0), round_id))
        except (TypeError, ValueError):
            await db.close()
            raise HTTPException(400, "Invalid jackpot")
    if "winning_numbers" in body:
        wn = body.get("winning_numbers")
        val = json.dumps(wn) if isinstance(wn, list) else (wn or None)
        await db.execute("UPDATE rounds SET winning_numbers=? WHERE id=?", (val, round_id))
    if "bonus_number" in body:
        b = body.get("bonus_number")
        await db.execute("UPDATE rounds SET bonus_number=? WHERE id=?", (int(b) if str(b).strip() not in ("", "None") else None, round_id))
    await db.commit()
    await db.close()
    return {"ok": True}


@app.delete("/api/platform/rounds/{round_id}")
async def platform_delete_round(round_id: int, request: Request):
    admin, db = await _require_platform_admin(request)
    cur = await db.execute("SELECT COUNT(*) AS n FROM participations WHERE round_id=?", (round_id,))
    if int((await cur.fetchone())["n"] or 0) > 0:
        await db.close()
        raise HTTPException(400, "Round has participants — cannot delete")
    await db.execute("DELETE FROM rounds WHERE id=?", (round_id,))
    await db.commit()
    await db.close()
    return {"ok": True}


def _notif_template_list(gid: int) -> list:
    """Templates for a scope (gid=0 platform, gid>0 group) with the guide + effective text."""
    out = []
    for key, t in NOTIF_TEMPLATES.items():
        default = t["default"]
        platform_text = _NOTIF_OVERRIDES.get((0, key)) or default
        if gid:
            effective = _NOTIF_OVERRIDES.get((gid, key)) or platform_text
            overridden = (gid, key) in _NOTIF_OVERRIDES
        else:
            effective = _NOTIF_OVERRIDES.get((0, key)) or default
            overridden = (0, key) in _NOTIF_OVERRIDES
        out.append({
            "key": key,
            "label": t["label"],
            "desc": t.get("desc", ""),
            "default": default,
            "inherited": platform_text,
            "text": effective,
            "overridden": overridden,
            "vars": describe_vars(effective or default),
        })
    return out


async def _set_notif_override(db, gid: int, key: str, text: str) -> bool:
    reset = text.strip() == "" or text.strip() == NOTIF_TEMPLATES[key]["default"].strip()
    await db.execute("DELETE FROM notif_templates WHERE group_id=? AND key=?", (gid, key))
    if not reset:
        await db.execute(
            "INSERT INTO notif_templates (group_id, key, text, updated_at) VALUES (?,?,?,datetime('now'))",
            (gid, key, text),
        )
    return reset


@app.get("/api/platform/notif-templates")
async def platform_notif_templates(request: Request):
    admin, db = await _require_platform_admin(request)
    await _load_notif_overrides(db)
    await db.close()
    return {"templates": _notif_template_list(0)}


@app.patch("/api/platform/notif-templates/{key}")
async def platform_update_notif_template(key: str, request: Request):
    admin, db = await _require_platform_admin(request)
    if key not in NOTIF_TEMPLATES:
        await db.close()
        raise HTTPException(404, "Unknown template")
    body = await request.json()
    text = "" if body.get("reset") else str(body.get("text") or "")
    reset = await _set_notif_override(db, 0, key, text)
    await db.commit()
    await _load_notif_overrides(db)
    await db.close()
    return {"ok": True, "reset": reset}


@app.post("/api/platform/notif-templates/{key}/test")
async def platform_test_notif_template(key: str, request: Request):
    """Send a sample of the message to the admin's own Telegram chat."""
    admin, db = await _require_platform_admin(request)
    await db.close()
    if key not in NOTIF_TEMPLATES:
        raise HTTPException(404, "Unknown template")
    body = await request.json()
    sample = NOTIF_TEMPLATES[key].get("sample", {})
    text = body.get("text")
    rendered = render_template(str(text), sample) if text else render_notif(key, **sample)
    await _notify(admin["telegram_id"], rendered)
    return {"ok": True, "sent_to": admin["telegram_id"], "preview": rendered}


# --- Trustee (group-admin) notification templates -----------------------------
@app.get("/api/admin/notif-templates")
async def admin_notif_templates(request: Request):
    user, db, group = await _require_group_trustee(request)
    await _load_notif_overrides(db)
    await db.close()
    return {"templates": _notif_template_list(group["id"])}


@app.patch("/api/admin/notif-templates/{key}")
async def admin_update_notif_template(key: str, request: Request):
    user, db, group = await _require_group_trustee(request)
    if key not in NOTIF_TEMPLATES:
        await db.close()
        raise HTTPException(404, "Unknown template")
    body = await request.json()
    text = "" if body.get("reset") else str(body.get("text") or "")
    reset = await _set_notif_override(db, group["id"], key, text)
    await db.commit()
    await _load_notif_overrides(db)
    await db.close()
    return {"ok": True, "reset": reset}


@app.post("/api/admin/notif-templates/{key}/test")
async def admin_test_notif_template(key: str, request: Request):
    """Send a sample of this group's message to the trustee's own Telegram."""
    user, db, group = await _require_group_trustee(request)
    gid = group["id"]
    await db.close()
    if key not in NOTIF_TEMPLATES:
        raise HTTPException(404, "Unknown template")
    body = await request.json()
    sample = NOTIF_TEMPLATES[key].get("sample", {})
    text = body.get("text")
    rendered = render_template(str(text), sample) if text else render_notif(key, group_id=gid, **sample)
    await _notify(user["telegram_id"], rendered)
    return {"ok": True, "sent_to": user["telegram_id"], "preview": rendered}


@app.patch("/api/platform/users/{telegram_id}")
async def platform_patch_user(
    telegram_id: int,
    request: Request,
    ):
    admin, db = await _require_platform_admin(request)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    target = await cur.fetchone()
    if not target:
        await db.close()
        raise HTTPException(404, "User not found")

    body = await request.json()

    if "group_id" in body:
        gid = body.get("group_id")
        if gid is None:
            await db.execute(
                "UPDATE users SET group_id=NULL WHERE telegram_id=?", (telegram_id,)
            )
        else:
            gid = int(gid)
            cur = await db.execute("SELECT id, status FROM groups WHERE id=?", (gid,))
            group = await cur.fetchone()
            if not group:
                await db.close()
                raise HTTPException(400, "Group not found")
            await db.execute(
                "UPDATE users SET group_id=? WHERE telegram_id=?", (gid, telegram_id)
            )

    if "is_platform_admin" in body:
        flag = 1 if body.get("is_platform_admin") else 0
        if telegram_id == admin["telegram_id"] and not flag:
            await db.close()
            raise HTTPException(400, "Cannot remove your own platform admin access")
        await db.execute(
            "UPDATE users SET is_platform_admin=? WHERE telegram_id=?",
            (flag, telegram_id),
        )

    if "credit" in body and body["credit"] is not None:
        await db.execute(
            "UPDATE users SET credit=? WHERE telegram_id=?",
            (float(body["credit"]), telegram_id),
        )

    await db.commit()
    cur = await db.execute("""
        SELECT u.*, g.name AS group_name, g.slug AS group_slug
        FROM users u
        LEFT JOIN groups g ON g.id = u.group_id
        WHERE u.telegram_id = ?
    """, (telegram_id,))
    row = await cur.fetchone()
    await db.close()
    return {"ok": True, "user": dict(row) if row else None}


# ---------------------------------------------------------------------------
# Stripe — inline Elements (no redirect)
# ---------------------------------------------------------------------------

@app.get("/api/stripe/config")
async def stripe_config():
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    return {"publishable_key": config.STRIPE_PUBLISHABLE_KEY}


def _app_base_url(request: Request) -> str:
    host = request.headers.get("host") or "lottochee.com"
    return f"https://{host}"


@app.post("/api/admin/group/stripe/connect")
async def admin_group_stripe_connect(request: Request):
    """Create (or resume) the trustee's Stripe Express account and return a
    hosted onboarding link. Member card top-ups are then charged directly on
    this account."""
    user, db, group = await _require_group_trustee(request)
    if not config.STRIPE_SECRET_KEY:
        await db.close()
        raise HTTPException(400, "Stripe not configured")
    gid = group["id"]
    acct_id = group.get("stripe_account_id")
    try:
        if not acct_id:
            acct = stripe.Account.create(
                type="express",
                country="CA",
                email=user.get("auth_email") or user.get("email") or None,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                business_type="individual",
                metadata={"group_id": str(gid), "trustee_id": str(user["telegram_id"])},
            )
            acct_id = acct.id
            await db.execute("UPDATE groups SET stripe_account_id=? WHERE id=?", (acct_id, gid))
            await db.commit()
        base = _app_base_url(request)
        link = stripe.AccountLink.create(
            account=acct_id,
            refresh_url=f"{base}/?stripe=refresh",
            return_url=f"{base}/?stripe=connected",
            type="account_onboarding",
        )
        await db.close()
        return {"url": link.url, "account_id": acct_id}
    except Exception as e:
        await db.close()
        log.exception("stripe connect error: %s", e)
        msg = getattr(e, "user_message", None) or str(e)
        if "signed up for Connect" in msg or "sign up for Connect" in msg:
            raise HTTPException(
                400,
                "Card payments aren’t enabled on the platform yet. The platform "
                "owner needs to turn on Stripe Connect once at "
                "dashboard.stripe.com/connect (then complete the platform profile). "
                "Until then, please use e-Transfer.",
            )
        raise HTTPException(400, f"Stripe Connect error: {msg}")


@app.post("/api/admin/broadcast")
async def admin_broadcast(request: Request):
    """Trustee sends a one-off message to every member of their group."""
    user, db, group = await _require_group_trustee(request)
    body = await request.json()
    message = (body.get("message") or "").strip()
    if not message:
        await db.close()
        raise HTTPException(400, "Message can't be empty")
    message = message[:2000]
    text = render_notif("broadcast", group_id=group["id"],
                        group=html.escape(group["name"]), message=html.escape(message))
    cur = await db.execute("SELECT COUNT(*) AS n FROM group_members WHERE group_id=?", (group["id"],))
    n = int((await cur.fetchone())["n"] or 0)
    await _notify_all(db, text, group_id=group["id"])
    await db.close()
    return {"ok": True, "sent": n}


@app.get("/api/admin/group/stripe/status")
async def admin_group_stripe_status(request: Request):
    """Live status of the trustee's connected Stripe account."""
    user, db, group = await _require_group_trustee(request)
    acct_id = group.get("stripe_account_id")
    if not acct_id or not config.STRIPE_SECRET_KEY:
        await db.close()
        return {"connected": False, "charges_enabled": False, "details_submitted": False, "account_id": None}
    try:
        acct = stripe.Account.retrieve(acct_id)
        ce = bool(acct.get("charges_enabled"))
        await db.execute(
            "UPDATE groups SET stripe_charges_enabled=? WHERE id=?", (1 if ce else 0, group["id"])
        )
        await db.commit()
        await db.close()
        return {
            "connected": True,
            "charges_enabled": ce,
            "payouts_enabled": bool(acct.get("payouts_enabled")),
            "details_submitted": bool(acct.get("details_submitted")),
            "account_id": acct_id,
        }
    except Exception as e:
        await db.close()
        log.warning("stripe status error: %s", e)
        return {"connected": True, "charges_enabled": False, "details_submitted": False,
                "account_id": acct_id, "error": str(e)}


GROUP_SUB_PRICE = 6.99


@app.get("/api/admin/group/subscription")
async def admin_group_subscription(request: Request):
    """Group's platform subscription status ($6.99/mo, billed on the platform)."""
    user, db, group = await _require_group_trustee(request, allow_locked=True)
    plan = group.get("pricing_plan") or "subscription"
    out = {
        "plan": plan,
        "required": plan == "subscription",
        "price": GROUP_SUB_PRICE,
        "status": group.get("platform_sub_status") or "none",
        "locked": group["status"] == "locked",
        "next_billing": None,
        "cancel_at_period_end": False,
    }
    sub_id = group.get("platform_sub_id")
    if sub_id and config.STRIPE_SECRET_KEY and out["status"] == "active":
        try:
            s = stripe.Subscription.retrieve(sub_id)
            out["next_billing"] = datetime.fromtimestamp(s["current_period_end"]).date().isoformat()
            out["cancel_at_period_end"] = bool(s.get("cancel_at_period_end"))
        except Exception:
            pass
    await db.close()
    return out


@app.post("/api/admin/group/subscription/create")
async def admin_group_subscription_create(request: Request):
    """Start the group's $6.99/mo platform subscription (collected on the platform
    Stripe account). Returns a client_secret to confirm the first payment."""
    user, db, group = await _require_group_trustee(request, allow_locked=True)
    if not config.STRIPE_SECRET_KEY:
        await db.close()
        raise HTTPException(400, "Stripe not configured")
    if (group.get("pricing_plan") or "subscription") != "subscription":
        await db.close()
        raise HTTPException(400, "This group is not on the subscription plan")
    if group.get("platform_sub_status") == "active":
        await db.close()
        raise HTTPException(400, "Subscription already active")
    try:
        customer_id = await _get_or_create_customer(user, db)
        price = stripe.Price.create(
            unit_amount=int(round(GROUP_SUB_PRICE * 100)),
            currency=config.CURRENCY.lower(),
            recurring={"interval": "month"},
            product_data={"name": f"LottoChee group plan — {group['name']}"},
        )
        sub = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            expand=["latest_invoice.payment_intent"],
            metadata={
                "kind": "group_plan",
                "group_id": str(group["id"]),
                "trustee_id": str(user["telegram_id"]),
            },
        )
        await db.execute(
            "UPDATE groups SET platform_sub_id=?, platform_sub_status='pending' WHERE id=?",
            (sub.id, group["id"]),
        )
        await db.commit()
        cs = sub.latest_invoice.payment_intent.client_secret
        await db.close()
        return {"client_secret": cs, "subscription_id": sub.id, "price": GROUP_SUB_PRICE}
    except Exception as e:
        await db.close()
        log.exception("group subscription create error: %s", e)
        msg = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Subscription error: {msg}")


@app.post("/api/admin/group/subscription/cancel")
async def admin_group_subscription_cancel(request: Request):
    """Trustee cancels the group subscription. The group is locked immediately —
    its data becomes inaccessible until the subscription is reactivated."""
    user, db, group = await _require_group_trustee(request, allow_locked=True)
    sub_id = group.get("platform_sub_id")
    if config.STRIPE_SECRET_KEY and sub_id:
        try:
            stripe.Subscription.cancel(sub_id)
        except Exception as e:
            msg = str(e)
            # Already gone at Stripe → fine to proceed and lock. Any other error
            # means it may still be billing, so don't lock — let them retry.
            if "resource_missing" not in msg and "No such subscription" not in msg:
                await db.close()
                log.warning("group subscription cancel error: %s", e)
                raise HTTPException(400, f"Could not cancel subscription: {getattr(e, 'user_message', None) or msg}")
    await db.execute(
        "UPDATE groups SET platform_sub_status='canceled', platform_sub_id=NULL, status='locked' "
        "WHERE id=?",
        (group["id"],),
    )
    await db.commit()
    await db.close()
    return {"ok": True, "locked": True}


@app.post("/api/stripe/payment-intent")
async def stripe_payment_intent(
    request: Request
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(request)
    gid, group = await _active_group_row(user, db)
    opts = _payment_options_payload(group, stripe_configured=True)
    if not opts["card_enabled"]:
        await db.close()
        if opts.get("card_setup_pending"):
            raise HTTPException(400, "Card top-up isn’t ready yet — your group's trustee is still connecting Stripe")
        raise HTTPException(400, "Card payments are not enabled for this group")
    acct_id = group.get("stripe_account_id")
    if not acct_id:
        await db.close()
        raise HTTPException(400, "Card top-up isn’t available — the group trustee hasn’t connected Stripe")
    body = await request.json()
    amount = round(float(body.get("amount", 0)), 2)
    if not is_valid_card_deposit_amount(amount):
        await db.close()
        raise HTTPException(400, "Card amount must be one of: $25, $50, $100, $250")
    charge_amount = amount
    try:
        # Direct charge on the trustee's connected account: funds and Stripe fees
        # settle on the trustee; the platform takes no application fee.
        pi = stripe.PaymentIntent.create(
            amount=int(charge_amount * 100),
            currency=config.CURRENCY.lower(),
            automatic_payment_methods={"enabled": True},
            metadata={
                "user_id": str(user["telegram_id"]),
                "telegram_id": str(user["telegram_id"]),
                "group_id": str(gid),
                "deposit_amount": str(amount),
            },
            stripe_account=acct_id,
        )
        await db.close()
        return {
            "client_secret": pi.client_secret,
            "charge_amount": charge_amount,
            "deposit_amount": amount,
            "stripe_account": acct_id,
        }
    except Exception as e:
        await db.close()
        log.exception("payment-intent error: %s", e)
        msg = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Payment error: {msg}")


@app.post("/api/stripe/subscription/create")
async def stripe_create_subscription(
    request: Request
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(request)
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["telegram_id"],),
    )
    if await cur.fetchone():
        raise HTTPException(400, "Already have an active subscription")
    _, group = await _active_group_row(user, db)
    opts = _payment_options_payload(group, stripe_configured=True)
    if not opts["card_enabled"]:
        await db.close()
        raise HTTPException(400, "Card payments are not enabled for this group")
    if group and group.get("stripe_account_id"):
        # Member funds route to the trustee's connected account, which uses
        # one-time direct charges. Recurring auto top-up isn't offered there.
        await db.close()
        raise HTTPException(400, "Monthly auto top-up isn’t available for this group — use a one-time card top-up")
    body = await request.json()
    amount = round(float(body.get("amount", 0)), 2)
    if not is_valid_card_deposit_amount(amount):
        await db.close()
        raise HTTPException(400, "Card amount must be one of: $25, $50, $100, $250")
    charge_amount = amount
    try:
        customer_id = await _get_or_create_customer(user, db)
        price = stripe.Price.create(
            unit_amount=int(charge_amount * 100),
            currency=config.CURRENCY.lower(),
            recurring={"interval": "month"},
            product_data={"name": "LottoChee Monthly Deposit"},
        )
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            expand=["latest_invoice.payment_intent"],
            metadata={
                "user_id": str(user["telegram_id"]),
                "telegram_id": str(user["telegram_id"]),
                "deposit_amount": str(amount),
            },
        )
        client_secret = subscription.latest_invoice.payment_intent.client_secret
        await db.close()
        return {"client_secret": client_secret, "subscription_id": subscription.id, "charge_amount": charge_amount, "deposit_amount": amount}
    except Exception as e:
        await db.close()
        log.exception("subscription/create error: %s", e)
        msg = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Subscription error: {msg}")


@app.get("/api/stripe/subscription")
async def stripe_get_subscription(request: Request):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(request)
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["telegram_id"],),
    )
    sub_row = await cur.fetchone()
    await db.close()
    if sub_row is None:
        return {"subscription": None}
    sub_dict = dict(sub_row)
    try:
        stripe_sub = stripe.Subscription.retrieve(sub_dict["stripe_sub_id"])
        sub_dict["next_billing"] = datetime.fromtimestamp(
            stripe_sub["current_period_end"]
        ).date().isoformat()
        sub_dict["cancel_at_period_end"] = stripe_sub.get("cancel_at_period_end", False)
    except Exception:
        sub_dict["next_billing"] = None
        sub_dict["cancel_at_period_end"] = False
    return {"subscription": sub_dict}


@app.post("/api/stripe/subscription/update")
async def stripe_update_subscription(
    request: Request
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(request)
    _, group = await _active_group_row(user, db)
    opts = _payment_options_payload(group, stripe_configured=True)
    if not opts["card_enabled"]:
        await db.close()
        raise HTTPException(400, "Card payments are not enabled for this group")
    body = await request.json()
    new_amount = round(float(body.get("amount", 0)), 2)
    if not is_valid_card_deposit_amount(new_amount):
        await db.close()
        raise HTTPException(400, "Card amount must be one of: $25, $50, $100, $250")
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["telegram_id"],),
    )
    sub_row = await cur.fetchone()
    if sub_row is None:
        await db.close()
        raise HTTPException(404, "No active subscription")
    stripe_sub = stripe.Subscription.retrieve(sub_row["stripe_sub_id"])
    product_id = stripe_sub["items"]["data"][0]["price"]["product"]
    new_price = stripe.Price.create(
        unit_amount=int(new_amount * 100),
        currency=config.CURRENCY.lower(),
        recurring={"interval": "month"},
        product=product_id,
    )
    stripe.Subscription.modify(
        sub_row["stripe_sub_id"],
        items=[{"id": stripe_sub["items"]["data"][0]["id"], "price": new_price.id}],
        proration_behavior="none",
    )
    await db.execute(
        "UPDATE stripe_subscriptions SET amount=?, updated_at=datetime('now') WHERE id=?",
        (new_amount, sub_row["id"]),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


@app.post("/api/stripe/subscription/cancel")
async def stripe_cancel_subscription(request: Request):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(request)
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["telegram_id"],),
    )
    sub_row = await cur.fetchone()
    if sub_row is None:
        raise HTTPException(404, "No active subscription")
    stripe.Subscription.modify(sub_row["stripe_sub_id"], cancel_at_period_end=True)
    await db.execute(
        "UPDATE stripe_subscriptions SET status='canceling', updated_at=datetime('now') WHERE id=?",
        (sub_row["id"],),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, config.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid Stripe signature")

    db = await get_db()

    if event["type"] == "payment_intent.succeeded":
        pi = event["data"]["object"]
        if pi.get("invoice"):
            # Part of a subscription invoice — handled by invoice.payment_succeeded
            await db.close()
            return {"ok": True}
        meta = pi.get("metadata", {})
        user_id = int(meta.get("user_id", 0))
        if user_id:
            # Credit deposit_amount (original, pre-fee); fall back to amount_received for legacy PIs
            deposit_amount = float(meta.get("deposit_amount") or 0)
            amount = deposit_amount if deposit_amount else pi["amount_received"] / 100
            group_id = int(meta.get("group_id") or 0) or None
            # Direct charges on a connected account arrive with event["account"] set.
            note = "Stripe card top-up (group account)" if event.get("account") else "Stripe one-time payment"
            await db.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (amount, user_id))
            await db.execute(
                "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
                (user_id, "deposit", amount, note, group_id),
            )
            await db.commit()

    elif event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        sub_id = invoice.get("subscription")
        if not sub_id:
            await db.close()
            return {"ok": True}
        # Application subscription ($6.99/mo before group exists): mark paid, auto-approve in 24h.
        acur = await db.execute(
            "SELECT * FROM trustee_applications WHERE stripe_sub_id=? AND status='pending'",
            (sub_id,),
        )
        app_row = await acur.fetchone()
        if app_row:
            auto_at = (
                datetime.now(timezone.utc) + timedelta(hours=TRUSTEE_AUTO_APPROVE_HOURS)
            ).strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                """UPDATE trustee_applications SET payment_status='paid', paid_at=datetime('now'),
                   auto_approve_at=? WHERE id=?""",
                (auto_at, app_row["id"]),
            )
            await db.commit()
            await db.close()
            return {"ok": True}
        # Group platform plan ($6.99/mo): activate and unlock the group.
        gcur = await db.execute("SELECT id FROM groups WHERE platform_sub_id=?", (sub_id,))
        grow = await gcur.fetchone()
        if grow:
            await db.execute(
                "UPDATE groups SET platform_sub_status='active', "
                "status=CASE WHEN status='locked' THEN 'active' ELSE status END WHERE id=?",
                (grow["id"],),
            )
            await db.commit()
            await db.close()
            return {"ok": True}
        cur = await db.execute(
            "SELECT * FROM stripe_subscriptions WHERE stripe_sub_id=? AND status='active'",
            (sub_id,),
        )
        sub_row = await cur.fetchone()
        user_id = None
        deposit_amount = 0.0
        if sub_row is None:
            # First payment — store the subscription record
            try:
                stripe_sub = stripe.Subscription.retrieve(sub_id)
                user_id = int(stripe_sub.metadata.get("user_id", 0))
                deposit_amount = float(stripe_sub.metadata.get("deposit_amount") or 0)
                if user_id:
                    stored_amount = deposit_amount or (
                        stripe_sub["items"]["data"][0]["price"]["unit_amount"] / 100
                    )
                    await db.execute(
                        "INSERT OR IGNORE INTO stripe_subscriptions "
                        "(user_id, stripe_sub_id, amount, status) VALUES (?,?,?,'active')",
                        (user_id, sub_id, stored_amount),
                    )
            except Exception as exc:
                log.error("Failed to store subscription: %s", exc)
        else:
            user_id = sub_row["user_id"]
            deposit_amount = sub_row["amount"]  # already stored as original pre-fee amount
        if user_id:
            amount = deposit_amount if deposit_amount else invoice.get("amount_paid", 0) / 100
            if amount > 0:
                await db.execute(
                    "UPDATE users SET credit=credit+? WHERE telegram_id=?", (amount, user_id)
                )
                await db.execute(
                    "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                    (user_id, "deposit", amount, "Stripe subscription billing"),
                )
                await db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"]["id"]
        await db.execute(
            "UPDATE stripe_subscriptions SET status='canceled', updated_at=datetime('now') "
            "WHERE stripe_sub_id=?",
            (sub_id,),
        )
        # Group platform plan ended (cancel or unpaid) — lock the group.
        await db.execute(
            "UPDATE groups SET platform_sub_status='canceled', platform_sub_id=NULL, status='locked' "
            "WHERE platform_sub_id=?",
            (sub_id,),
        )
        await db.commit()

    await db.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Payment result page (fallback for 3DS redirect)
# ---------------------------------------------------------------------------

_CLOSE_PAGE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body {{ font-family: sans-serif; display:flex; align-items:center; justify-content:center;
           height:100vh; margin:0; background:#17212b; color:#f5f5f5;
           flex-direction:column; gap:12px; }}
  </style>
</head>
<body>
  <h2>{icon}</h2>
  <p>{msg}</p>
  <script>
    setTimeout(() => {{
      if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) {{
        window.Telegram.WebApp.close();
      }} else {{
        window.location.href = '/activity';
      }}
    }}, 2000);
  </script>
</body>
</html>"""


@app.get("/payment-success", response_class=HTMLResponse)
async def payment_success():
    return _CLOSE_PAGE.format(title="Success", icon="✅", msg="Payment successful! Closing…")


@app.get("/payment-cancel", response_class=HTMLResponse)
async def payment_cancel():
    return _CLOSE_PAGE.format(title="Cancelled", icon="❌", msg="Payment cancelled. Closing…")


# ---------------------------------------------------------------------------
# Static files — must be last
# ---------------------------------------------------------------------------

class _SPAStaticFiles(StaticFiles):
    """Serve the built Mini App, but never let HTML be cached.

    Asset files are content-hashed (index-<hash>.js/.css) so they cache safely
    forever, but index.html references those hashes. If a client — especially
    Telegram's in-app webview, which caches aggressively — holds a stale
    index.html, it keeps loading the old bundle and never sees new deploys.
    Forcing no-cache on HTML guarantees the latest build is always picked up.
    """

    @staticmethod
    def _is_private_spa_path(path: str) -> bool:
        clean = path.strip("/")
        if clean in {"login", "topup", "rounds", "activity", "profile", "admin", "platform"}:
            return True
        return clean.startswith(("join/", "round/"))

    async def get_response(self, path, scope):
        original_path = path
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None
        # SPA fallback: client-side routes like /profile have no file on disk.
        # Serve index.html for any not-found path that isn't an asset request
        # (i.e. has no file extension), so a hard refresh / direct link works.
        # Never fall back for backend paths — an unmatched /api/* must stay a
        # real 404 (JSON), otherwise the frontend would try to JSON.parse HTML.
        _backend = ("api/", "telegram-webhook", "payment-success", "payment-cancel")
        if response is None or response.status_code == 404:
            is_asset = "." in path.rsplit("/", 1)[-1]
            is_backend = path.startswith(_backend)
            if not is_asset and not is_backend:
                response = await super().get_response("index.html", scope)
            elif response is None:
                raise StarletteHTTPException(status_code=404)
        media = response.headers.get("content-type", "")
        if path in (".", "") or path.endswith(".html") or media.startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            if self._is_private_spa_path(original_path):
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
        elif original_path.replace("\\", "/").lstrip("./").startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
        return response


app.mount("/", _SPAStaticFiles(directory="mini_app/dist", html=True), name="static")
