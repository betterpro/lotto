"""
FastAPI application — serves the REST API, the React Mini App static files,
the Telegram bot webhook, and Stripe payment endpoints.
"""

import asyncio
import base64
import email as _email_lib
import hashlib
import hmac
import imaplib
import json
import logging
import os
import random
import re
from contextlib import asynccontextmanager
from datetime import date, datetime
from email.utils import parseaddr
from urllib.parse import parse_qsl

import stripe
from anthropic import AsyncAnthropic
from fastapi import FastAPI, Header, HTTPException, Request
import httpx
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application

import config
from agreements import (
    build_master_agreement,
    build_round_agreement,
    build_trustee_from_user,
    lottery_label,
)
from lottery_types import LOTTERY_PREFERENCE_PRICES, lottery_share_price, valid_lottery_type
from group_context import (
    CARD_DEPOSIT_AMOUNTS,
    VALID_PAYMENT_METHODS,
    add_group_member,
    enrich_user_context,
    ensure_active_group_id,
    get_group,
    get_group_by_slug,
    get_trustee_user,
    get_user_groups,
    group_allows_payment,
    group_public,
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
from bot import build_application
from database import get_db

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
            if (my_prize or 0) > 0:
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


async def _get_user(init_data: str, db):
    params = _validate_init_data(init_data)
    if params is None:
        raise HTTPException(401, "Invalid initData")
    user_json = params.get("user")
    if not user_json:
        raise HTTPException(401, "No user in initData")
    tg = json.loads(user_json)
    start_param = _init_start_param(params)
    invite_slug = parse_invite_slug(start_param)
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


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def _open_app_markup() -> InlineKeyboardMarkup | None:
    if not _bot_username:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Open Lotto Chee 🎟", url=f"https://t.me/{_bot_username}?startapp=open")
    ]])


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


async def _upload_ticket_to_storage(round_id: int, image_bytes: bytes, media_type: str) -> str:
    """Upload ticket image to Supabase Storage bucket 'tickets'; return public URL."""
    ext = "jpg" if "jpeg" in media_type else media_type.split("/")[-1]
    path = f"round-{round_id}.{ext}"
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
            await _notify(u["telegram_id"],
                f"⚠️ <b>Auto-join skipped — Round #{round_id}</b>\n"
                f"Balance ${u['credit']:.2f} is less than ${amount:.2f} needed.\n"
                f"Top up your account to stay in the next draw! 🎟")
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
        await _notify(u["telegram_id"],
            f"🎟 <b>Auto-joined Round #{round_id}</b>\n"
            f"{shares} share{'s' if shares > 1 else ''} · <b>${amount:.2f}</b> deducted\n"
            f"Remaining balance: ${bal:.2f}")


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
    await _notify(
        dep["user_id"],
        f"✅ <b>E-transfer received — ${dep['amount']:.2f}</b>\n"
        f"Your account has been credited.",
    )
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


async def _auth(x_init_data: str | None):
    if not x_init_data:
        raise HTTPException(401, "Missing X-Init-Data header")
    db = await get_db()
    user = await _get_user(x_init_data, db)
    return user, db


async def _require_group_trustee(x_init_data):
    user, db = await _auth(x_init_data)
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
    return user, db, group


async def _require_platform_admin(x_init_data):
    user, db = await _auth(x_init_data)
    if not user.get("is_platform_admin") and user["telegram_id"] not in config.PLATFORM_ADMIN_IDS:
        raise HTTPException(403, "Platform admin only")
    return user, db


# Backward-compatible alias
async def _require_trustee(x_init_data):
    user, db, _group = await _require_group_trustee(x_init_data)
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
    global _ptb_app, _bot_username, _etransfer_task
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
    yield
    if _etransfer_task:
        _etransfer_task.cancel()
        try:
            await _etransfer_task
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
# /api/me
# ---------------------------------------------------------------------------

@app.get("/api/me")
async def api_me(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def api_group_join(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def api_groups_list(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
            "link": f"https://t.me/{_bot_username}?start=g_{slug}",
            "app_link": f"https://t.me/{_bot_username}?startapp=join_{slug}",
        })
    return {"groups": groups, "active_group_id": active_gid}


@app.post("/api/groups/active")
async def api_groups_set_active(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def api_invite(
    group_id: int | None = None,
    x_init_data: str | None = Header(default=None),
):
    user, db = await _auth(x_init_data)
    gid = group_id or user.get("group_id")
    if not gid:
        gid = await ensure_active_group_id(db, user)
    if not gid or not await user_in_group(db, user["telegram_id"], gid):
        await db.close()
        raise HTTPException(403, "Join this group before sharing invites")
    group = await get_group(db, gid)
    await db.close()
    if not _bot_username:
        raise HTTPException(500, "Bot not available")
    if not group:
        raise HTTPException(404, "Group not found")
    slug = group["slug"]
    link = f"https://t.me/{_bot_username}?start=g_{slug}"
    app_link = f"https://t.me/{_bot_username}?startapp=join_{slug}"
    return {
        "link": link,
        "app_link": app_link,
        "slug": slug,
        "group_id": gid,
        "group_name": group["name"],
    }


# ---------------------------------------------------------------------------
# /api/agreement
# ---------------------------------------------------------------------------

async def _trustee_for_user(db, user: dict):
    group = await get_group(db, user.get("group_id"))
    if not group:
        return None
    return await get_trustee_user(db, group["trustee_user_id"])


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
async def api_update_profile_email(request: Request, x_init_data: str | None = Header(default=None)):
    """Save Interac e-transfer sender email only (Profile page)."""
    user, db = await _auth(x_init_data)
    body = await request.json()
    email_addr = (body.get("email") or "").strip().lower()
    if not email_addr or "@" not in email_addr:
        await db.close()
        raise HTTPException(400, "Valid email required")
    await db.execute(
        "UPDATE users SET email=? WHERE telegram_id=?", (email_addr, user["telegram_id"])
    )
    await db.commit()
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    await db.close()
    return {"ok": True, "user": dict(row) if row else None}


@app.post("/api/beneficiary")
async def api_save_beneficiary(request: Request, x_init_data: str | None = Header(default=None)):
    """Persist beneficiary profile from onboarding (BCLC Group Prize Agreement)."""
    user, db = await _auth(x_init_data)
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
async def api_agreement_master(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    u = dict(row) if row else dict(user)
    trustee = await _trustee_dict_for_user(db, u)
    body = build_master_agreement(**_beneficiary_agreement_kwargs(u), trustee=trustee)
    await db.close()
    return {
        "title": "Group Prize Agreement",
        "body": body,
    }


@app.get("/api/agreement/master/download")
async def api_agreement_master_download(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute("SELECT * FROM users WHERE telegram_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    u = dict(row) if row else dict(user)
    kwargs = _beneficiary_agreement_kwargs(u)
    trustee = await _trustee_dict_for_user(db, u)
    body = build_master_agreement(**kwargs, trustee=trustee)
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
async def api_agreement_round(round_id: int, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    await _auto_close_round_if_due(db, round_id)
    cur = await db.execute(
        "SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, user.get("group_id"))
    )
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
    )
    await db.close()
    return {
        "title": f"Round #{round_id} Draw Agreement",
        "body": body,
        "round_id": round_id,
    }


@app.get("/api/agreement/round/{round_id}/download")
async def api_agreement_round_download(round_id: int, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    await _auto_close_round_if_due(db, round_id)
    cur = await db.execute(
        "SELECT * FROM rounds WHERE id=? AND group_id=?", (round_id, user.get("group_id"))
    )
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

async def _build_round_detail(db, round_, user_id: int) -> dict:
    await _auto_close_round_if_due(db, round_["id"])
    cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_["id"],))
    refreshed = await cur.fetchone()
    if refreshed:
        round_ = refreshed
    rd = dict(round_)
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
    rd["my_pct"]    = my["pct"]    if my else None
    rd["my_won"]    = my["won"]    if my else None
    rd["pool_target"] = (rd.get("tickets_target") or 25) * (rd.get("price_per_share") or 5)
    rd["has_ticket_image"] = bool(rd.get("ticket_image"))
    rd.pop("ticket_image", None)
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
    if rd.get("winner_id"):
        cur = await db.execute(
            "SELECT full_name, username FROM users WHERE telegram_id=?", (rd["winner_id"],)
        )
        w = await cur.fetchone()
        rd["winner_name"] = (w["full_name"] or w["username"]) if w else None
    else:
        rd["winner_name"] = None
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
    card_allowed = bool(group and group_allows_payment(group, "card") and stripe_configured)
    etx_allowed = bool(group and group_allows_payment(group, "etransfer") and admin_email)
    etx_presets = [a for a in CARD_DEPOSIT_AMOUNTS if a >= min_amt]
    return {
        "payment_methods": group_public(group)["payment_methods"] if group else "both",
        "etransfer_min_amount": min_amt,
        "card_amounts": list(CARD_DEPOSIT_AMOUNTS),
        "etransfer_amounts": etx_presets,
        "card_enabled": card_allowed,
        "etransfer_enabled": etx_allowed,
        "etransfer_email": admin_email if etx_allowed else None,
    }


@app.get("/api/round")
async def api_round(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def api_open_rounds(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def api_rounds(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
        rd["pool_target"] = (rd.get("tickets_target") or 25) * (rd.get("price_per_share") or 5)
        rd["participants_count"] = int(rd.get("participants_count") or 0)
        rd["participants"] = rd["participants_count"]
        rd["my_pct"] = round((rd["my_stake"] / rd["pool"]) * 100, 1) if rd.get("my_stake") and rd.get("pool") else None
        rd["has_ticket_image"] = bool(rd.get("ticket_image"))
        rd.pop("ticket_image", None)
        rounds.append(rd)
    await db.close()
    return {"rounds": rounds}


# ---------------------------------------------------------------------------
# /api/participate
# ---------------------------------------------------------------------------

@app.post("/api/participate")
async def api_participate(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
    await db.close()
    return {"ok": True, "my_pct": my_pct}


# ---------------------------------------------------------------------------
# /api/transactions
# ---------------------------------------------------------------------------

@app.get("/api/transactions")
async def api_transactions(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def api_deposit(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
)

_LOTTERY_SHARE_PRICE = LOTTERY_PREFERENCE_PRICES


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
    }


@app.get("/api/settings")
async def get_settings(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute("SELECT * FROM user_settings WHERE user_id=?", (user["telegram_id"],))
    row = await cur.fetchone()
    await db.close()
    return _row_to_settings(row)


@app.put("/api/settings")
async def put_settings(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    b = await request.json()
    lottery_pref = b.get("lottery_preference", "both")
    if lottery_pref not in _LOTTERY_SHARE_PRICE:
        lottery_pref = "both"
    await db.execute("""
        INSERT INTO user_settings
            (user_id, auto_participate, shares_per_round, max_rounds_per_month,
             preferred_day, lottery_preference,
             notif_new_round, notif_reminder, notif_ticket, notif_results, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
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
    ))
    await db.commit()
    await db.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# E-transfer endpoints
# ---------------------------------------------------------------------------

@app.get("/api/payment/options")
async def payment_options(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    try:
        _, group = await _active_group_row(user, db)
    except HTTPException:
        group = await get_group(db, user.get("group_id")) if user.get("group_id") else None
    payload = _payment_options_payload(group, stripe_configured=bool(config.STRIPE_SECRET_KEY))
    await db.close()
    return payload


@app.get("/api/etransfer/info")
async def etransfer_info(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
async def etransfer_deposit(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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

@app.get("/api/trustee/application")
async def api_trustee_application_status(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute(
        """SELECT * FROM trustee_applications
           WHERE applicant_user_id = ? ORDER BY id DESC LIMIT 1""",
        (user["telegram_id"],),
    )
    app_row = await cur.fetchone()
    await db.close()
    return {"application": dict(app_row) if app_row else None}


@app.post("/api/trustee/apply")
async def api_trustee_apply(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
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
    await db.execute(
        "INSERT INTO trustee_applications (applicant_user_id, proposed_group_name) VALUES (?,?)",
        (user["telegram_id"], name),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin endpoints (group trustee)
# ---------------------------------------------------------------------------

@app.get("/api/admin/group")
async def admin_get_group(x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
    await db.close()
    return {
        "group": {
            **group_public(group),
            "stripe_configured": bool(config.STRIPE_SECRET_KEY),
        }
    }


@app.patch("/api/admin/group")
async def admin_patch_group(request: Request, x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
    body = await request.json()
    gid = group["id"]

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
async def admin_round(x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
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
async def admin_rounds(x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
    gid = group["id"]
    cur = await db.execute(
        "SELECT * FROM rounds WHERE group_id=? AND status IN ('open','closed','uploaded','drawn') "
        "ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'closed' THEN 1 WHEN 'uploaded' THEN 2 ELSE 3 END, "
        f"{_OPEN_ROUNDS_ORDER}",
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


@app.post("/api/admin/round/new")
async def admin_new_round(request: Request, x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
    gid = group["id"]
    body = await request.json()
    jackpot = body.get("jackpot") or 0
    tickets_target = body.get("tickets_target") or 25
    price_per_share = body.get("price_per_share") or 5.0
    draw_date = body.get("draw_date") or None
    lottery_type = body.get("lottery_type") or "lotto_max"
    if not valid_lottery_type(lottery_type):
        await db.close()
        raise HTTPException(400, "Unknown lottery type")
    cur = await db.execute(
        """INSERT INTO rounds
           (status, draw_date, jackpot, tickets_target, price_per_share, lottery_type, group_id)
           VALUES ('open', ?, ?, ?, ?, ?, ?) RETURNING id""",
        (draw_date, jackpot, tickets_target, price_per_share, lottery_type, gid),
    )
    round_id = cur.lastrowid
    await db.commit()

    await _auto_join_round(db, round_id, price_per_share, group_id=gid)

    draw_str = f" · Draw {draw_date}" if draw_date else ""
    jackpot_str = f" · ${jackpot/1_000_000:.0f}M jackpot" if jackpot else ""
    await _notify_all(db,
        f"🎟 <b>New round opened — #{round_id}</b>{draw_str}{jackpot_str}\n"
        f"${price_per_share:.0f}/share · target {tickets_target} tickets",
        setting_col="notif_new_round",
        group_id=gid,
    )

    await db.close()
    return {"ok": True, "round_id": round_id}


@app.post("/api/admin/round/close")
async def admin_close_round(request: Request, x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
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
    await db.close()
    return {"ok": True, "round_id": round_["id"]}


@app.post("/api/admin/round/upload-ticket")
async def admin_upload_ticket(request: Request, x_init_data: str | None = Header(default=None)):
    """Admin uploads ticket numbers for a round (sets status to 'uploaded')."""
    user, db, group = await _require_group_trustee(x_init_data)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    numbers = body.get("numbers", [])  # list of 7 ints

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

    await db.execute(
        "UPDATE rounds SET ticket_numbers=?, status='uploaded' WHERE id=?",
        (json.dumps(numbers), round_["id"])
    )
    await db.commit()

    # Notify participants: ticket purchased
    draw_date_str = round_["draw_date"] or "TBD"
    nums_str = "  ".join(f"<b>{n}</b>" for n in numbers)
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
            msg_parts.append(
                f"✅ <b>Ticket purchased — Round #{round_['id']}</b>\n"
                f"Numbers: {nums_str}"
            )
        if notif_reminder:
            msg_parts.append(f"⏰ Draw date: <b>{draw_date_str}</b> — good luck! 🍀")
        if msg_parts:
            await _notify(uid, "\n".join(msg_parts))

    await db.close()
    return {"ok": True, "round_id": round_["id"]}


@app.post("/api/admin/round/scan-ticket")
async def admin_scan_ticket(request: Request, x_init_data: str | None = Header(default=None)):
    """Scan a ticket photo with Claude Vision to extract numbers and draw date."""
    user, db, group = await _require_group_trustee(x_init_data)
    gid = group["id"]

    if not config.ANTHROPIC_API_KEY:
        await db.close()
        raise HTTPException(400, "Ticket scanning not configured (set ANTHROPIC_API_KEY)")

    body = await request.json()
    round_id = body.get("round_id")
    image_data = body.get("image_b64", "")

    if not image_data:
        await db.close()
        raise HTTPException(400, "No image provided")

    # Strip data URL prefix, detect media type
    media_type = "image/jpeg"
    if image_data.startswith("data:"):
        header, image_data = image_data.split(",", 1)
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

    client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": image_data},
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a Canadian Lotto Max lottery ticket. "
                            "Extract and return ONLY a JSON object with no extra text:\n"
                            "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
                            "- numbers: array of exactly 7 integers 1-50 from the FIRST selection (null if not visible)\n"
                            "Example: {\"draw_date\":\"2025-03-14\",\"numbers\":[3,14,22,31,38,45,49]}"
                        ),
                    },
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

    # Upload to Supabase Storage if configured, otherwise fall back to storing base64 in DB
    img_bytes = base64.b64decode(image_data)
    if config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY:
        try:
            storage_url = await _upload_ticket_to_storage(round_["id"], img_bytes, media_type)
            await db.execute("UPDATE rounds SET ticket_image=? WHERE id=?", (storage_url, round_["id"]))
            log.info("Ticket uploaded to Storage: %s", storage_url)
        except Exception as exc:
            log.warning("Storage upload failed, storing base64 in DB: %s", exc)
            await db.execute("UPDATE rounds SET ticket_image=? WHERE id=?", (image_data, round_["id"]))
    else:
        await db.execute("UPDATE rounds SET ticket_image=? WHERE id=?", (image_data, round_["id"]))
    await db.commit()
    await db.close()

    numbers = result.get("numbers")
    if isinstance(numbers, list):
        numbers = [int(n) for n in numbers if isinstance(n, (int, float)) and 1 <= int(n) <= 50][:7]

    return {
        "ok": True,
        "round_id": round_["id"],
        "draw_date": result.get("draw_date"),
        "numbers": numbers or [],
    }


@app.get("/api/round/{round_id}/ticket-image")
async def round_ticket_image(round_id: int, x_init_data: str | None = Header(default=None)):
    """Serve the stored ticket image for any authenticated user."""
    user, db = await _auth(x_init_data)
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


@app.post("/api/admin/round/results")
async def admin_enter_results(request: Request, x_init_data: str | None = Header(default=None)):
    """Admin enters winning numbers and total prize; prizes distributed proportionally."""
    user, db, group = await _require_group_trustee(x_init_data)
    gid = group["id"]
    body = await request.json()
    round_id = body.get("round_id")
    winning_numbers = body.get("winning_numbers", [])
    bonus_number = body.get("bonus_number")
    total_prize = float(body.get("total_prize", 0))

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

    # Get all participations
    cur = await db.execute("SELECT * FROM participations WHERE round_id=?", (round_["id"],))
    parts = await cur.fetchall()
    pool = round_["pool"] or sum(p["amount"] for p in parts)

    if not winning_numbers:
        await db.close()
        raise HTTPException(400, "Winning numbers are required")

    # Distribute prize proportionally (always set participation.prize so WON/LOST is accurate)
    for p in parts:
        share = p["amount"] / pool if pool else 0
        prize = round(share * total_prize, 2) if total_prize > 0 and pool > 0 else 0.0
        await db.execute(
            "UPDATE participations SET prize=? WHERE round_id=? AND user_id=?",
            (prize, round_["id"], p["user_id"]),
        )
        if prize > 0:
            await db.execute(
                "UPDATE users SET credit=credit+? WHERE telegram_id=?", (prize, p["user_id"])
            )
            await db.execute(
                "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
                (p["user_id"], "win", prize, f"Prize Round #{round_['id']}", gid),
            )

    await db.execute(
        "UPDATE rounds SET status='drawn', winning_numbers=?, bonus_number=?, drawn_at=datetime('now') WHERE id=?",
        (json.dumps(winning_numbers), bonus_number, round_["id"]),
    )
    await db.commit()

    # Notify each participant individually with their result
    win_str = "  ".join(f"<b>{n}</b>" for n in winning_numbers)
    if bonus_number:
        win_str += f"  +<b>{bonus_number}</b> (bonus)"
    for p in parts:
        setting = await db.execute(
            "SELECT notif_results FROM user_settings WHERE user_id=?", (p["user_id"],)
        )
        s = await setting.fetchone()
        if s and not s["notif_results"]:
            continue
        prize = p.get("prize", 0) or 0
        share_pct = round(p["amount"] / pool * 100, 1) if pool else 0
        if prize > 0:
            msg = (
                f"🏆 <b>You won — Round #{round_['id']}</b>\n"
                f"Prize: <b>${prize:.2f}</b> (your {share_pct}% share)\n"
                f"Winning numbers: {win_str}\n"
                f"Credited to your balance! 💰"
            )
        else:
            msg = (
                f"🎟 <b>Results — Round #{round_['id']}</b>\n"
                f"Winning numbers: {win_str}\n"
                f"Your stake: ${p['amount']:.2f} ({share_pct}%)\n"
                f"No prize this time — better luck next round! 🍀"
            )
        await _notify(p["user_id"], msg)

    await db.close()
    return {"ok": True, "total_prize": total_prize, "distributed": len(parts)}


@app.post("/api/admin/round/draw")
async def admin_draw(x_init_data: str | None = Header(default=None)):
    """
    LEGACY / DEPRECATED: Old random winner-takes-all draw.
    New flow: use /api/admin/round/upload-ticket then /api/admin/round/results.
    Kept for backward compatibility only — calls results with total_prize=0.
    """
    user, db, group = await _require_group_trustee(x_init_data)
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
async def admin_deposits(x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
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
    req_id: int, request: Request, x_init_data: str | None = Header(default=None)
):
    user, db, group = await _require_group_trustee(x_init_data)
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
        await db.execute(
            "UPDATE users SET credit=credit+? WHERE telegram_id=?", (dep["amount"], dep["user_id"])
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note, group_id) VALUES (?,?,?,?,?)",
            (dep["user_id"], "deposit", dep["amount"], f"Approved deposit #{req_id}", gid),
        )
        await db.execute(
            "UPDATE deposit_requests SET status='approved', resolved_at=datetime('now') WHERE id=?",
            (req_id,)
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
async def admin_members(x_init_data: str | None = Header(default=None)):
    user, db, group = await _require_group_trustee(x_init_data)
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
async def admin_check_etransfer(x_init_data: str | None = Header(default=None)):
    """Manually trigger IMAP check to auto-approve matched e-transfer deposits."""
    user, db, _group = await _require_group_trustee(x_init_data)
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
async def platform_overview(x_init_data: str | None = Header(default=None)):
    user, db = await _require_platform_admin(x_init_data)
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
async def platform_groups(x_init_data: str | None = Header(default=None)):
    user, db = await _require_platform_admin(x_init_data)
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
async def platform_group_detail(group_id: int, x_init_data: str | None = Header(default=None)):
    await _require_platform_admin(x_init_data)
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
    x_init_data: str | None = Header(default=None),
    limit: int = 100,
    group_id: int | None = None,
):
    await _require_platform_admin(x_init_data)
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
    x_init_data: str | None = Header(default=None),
    group_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
):
    user, db = await _require_platform_admin(x_init_data)
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
async def platform_applications(x_init_data: str | None = Header(default=None)):
    user, db = await _require_platform_admin(x_init_data)
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
async def platform_approve_application(
    app_id: int, x_init_data: str | None = Header(default=None)
):
    admin, db = await _require_platform_admin(x_init_data)
    cur = await db.execute("SELECT * FROM trustee_applications WHERE id=?", (app_id,))
    app_row = await cur.fetchone()
    if not app_row or app_row["status"] != "pending":
        await db.close()
        raise HTTPException(404, "Pending application not found")
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
    cur = await db.execute(
        """INSERT INTO groups (name, slug, trustee_user_id, status)
           VALUES (?,?,?, 'active') RETURNING id""",
        (app_row["proposed_group_name"], slug, applicant_id),
    )
    group_id = cur.lastrowid
    await db.execute(
        "UPDATE users SET group_id=? WHERE telegram_id=?", (group_id, applicant_id)
    )
    await add_group_member(db, group_id, applicant_id, "trustee")
    await db.execute(
        """UPDATE trustee_applications SET status='approved', reviewed_by=?,
           reviewed_at=datetime('now') WHERE id=?""",
        (admin["telegram_id"], app_id),
    )
    await db.commit()
    await db.close()
    return {"ok": True, "group_id": group_id, "slug": slug}


@app.post("/api/platform/applications/{app_id}/reject")
async def platform_reject_application(
    app_id: int, request: Request, x_init_data: str | None = Header(default=None)
):
    admin, db = await _require_platform_admin(x_init_data)
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
    group_id: int, request: Request, x_init_data: str | None = Header(default=None)
):
    await _require_platform_admin(x_init_data)
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
    detail = await platform_group_detail(group_id, x_init_data)
    return {"ok": True, **detail}


@app.patch("/api/platform/users/{telegram_id}")
async def platform_patch_user(
    telegram_id: int,
    request: Request,
    x_init_data: str | None = Header(default=None),
):
    admin, db = await _require_platform_admin(x_init_data)
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


@app.post("/api/stripe/payment-intent")
async def stripe_payment_intent(
    request: Request, x_init_data: str | None = Header(default=None)
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
    _, group = await _active_group_row(user, db)
    opts = _payment_options_payload(group, stripe_configured=True)
    if not opts["card_enabled"]:
        await db.close()
        raise HTTPException(400, "Card payments are not enabled for this group")
    body = await request.json()
    amount = round(float(body.get("amount", 0)), 2)
    if not is_valid_card_deposit_amount(amount):
        await db.close()
        raise HTTPException(400, "Card amount must be one of: $25, $50, $100, $250")
    charge_amount = amount
    try:
        customer_id = await _get_or_create_customer(user, db)
        pi = stripe.PaymentIntent.create(
            amount=int(charge_amount * 100),
            currency=config.CURRENCY.lower(),
            customer=customer_id,
            automatic_payment_methods={"enabled": True},
            metadata={
                "user_id": str(user["telegram_id"]),
                "telegram_id": str(user["telegram_id"]),
                "deposit_amount": str(amount),
            },
        )
        await db.close()
        return {"client_secret": pi.client_secret, "charge_amount": charge_amount, "deposit_amount": amount}
    except Exception as e:
        await db.close()
        log.exception("payment-intent error: %s", e)
        msg = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Payment error: {msg}")


@app.post("/api/stripe/subscription/create")
async def stripe_create_subscription(
    request: Request, x_init_data: str | None = Header(default=None)
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
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
            product_data={"name": "Lotto Chee Monthly Deposit"},
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
async def stripe_get_subscription(x_init_data: str | None = Header(default=None)):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
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
    request: Request, x_init_data: str | None = Header(default=None)
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
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
async def stripe_cancel_subscription(x_init_data: str | None = Header(default=None)):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
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
        user_id = int(pi.get("metadata", {}).get("user_id", 0))
        if user_id:
            # Credit deposit_amount (original, pre-fee); fall back to amount_received for legacy PIs
            deposit_amount = float(pi.get("metadata", {}).get("deposit_amount") or 0)
            amount = deposit_amount if deposit_amount else pi["amount_received"] / 100
            await db.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (amount, user_id))
            await db.execute(
                "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                (user_id, "deposit", amount, "Stripe one-time payment"),
            )
            await db.commit()

    elif event["type"] == "invoice.payment_succeeded":
        invoice = event["data"]["object"]
        sub_id = invoice.get("subscription")
        if not sub_id:
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
      if (window.Telegram && window.Telegram.WebApp) window.Telegram.WebApp.close();
      else window.close();
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

app.mount("/", StaticFiles(directory="mini_app/dist", html=True), name="static")
