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
from urllib.parse import parse_qsl

import stripe
from anthropic import AsyncAnthropic
from fastapi import FastAPI, Header, HTTPException, Request
import httpx
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from telegram import Update
from telegram.ext import Application

import config
from bot import build_application
from database import get_db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

if config.STRIPE_SECRET_KEY:
    stripe.api_key = config.STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def display_status(status: str, draw_date_str=None) -> str:
    if status == 'drawn':
        return 'DRAWN'
    if status in ('uploaded', 'closed'):
        return 'UPLOADED'
    if status != 'open':
        return 'DRAWN'
    if not draw_date_str:
        return 'OPEN'
    try:
        draw = date.fromisoformat(draw_date_str)
    except ValueError:
        return 'OPEN'
    today = date.today()
    if (draw - today).days <= 1:
        return 'CLOSING'
    return 'OPEN'


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


async def _get_user(init_data: str, db):
    params = _validate_init_data(init_data)
    if params is None:
        raise HTTPException(401, "Invalid initData")
    user_json = params.get("user")
    if not user_json:
        raise HTTPException(401, "No user in initData")
    tg = json.loads(user_json)
    row = await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg["id"],))
    user = await row.fetchone()
    if user is None:
        # Auto-register on first Mini App open using Telegram initData
        full_name = " ".join(filter(None, [
            tg.get("first_name", ""), tg.get("last_name", "")
        ])).strip() or tg.get("username") or f"user_{tg['id']}"
        is_trustee = 1 if tg["id"] == config.TRUSTEE_ID else 0
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, full_name, is_trustee) VALUES (?,?,?,?)",
            (tg["id"], tg.get("username"), full_name, is_trustee),
        )
        await db.execute(
            "INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (tg["id"],)
        )
        await db.commit()
        row = await db.execute("SELECT * FROM users WHERE telegram_id=?", (tg["id"],))
        user = await row.fetchone()
    user = dict(user)
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

async def _notify(telegram_id: int, text: str):
    """Send a Telegram message. Silently swallows errors (user may have blocked bot)."""
    if _ptb_app is None:
        return
    try:
        await _ptb_app.bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
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


async def _notify_all(db, text: str, setting_col: str | None = None):
    """Notify all users, optionally filtering by a user_settings boolean column."""
    if setting_col:
        cur = await db.execute(f"""
            SELECT u.telegram_id FROM users u
            LEFT JOIN user_settings s ON s.user_id = u.telegram_id
            WHERE COALESCE(s.{setting_col}, 1) = 1
        """)
    else:
        cur = await db.execute("SELECT telegram_id FROM users")
    for row in await cur.fetchall():
        await _notify(row["telegram_id"], text)


async def _auto_join_round(db, round_id: int, price_per_share: float):
    """Auto-enter users who opted in, have balance, and haven't hit their monthly limit."""
    from datetime import date as _date
    month_start = _date.today().replace(day=1).isoformat()

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
        amount = shares * _LOTTERY_SHARE_PRICE.get(pref, price_per_share)

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


def _imap_find_lotto_refs() -> list[int]:
    """Synchronous IMAP scan. Returns deposit IDs referenced in Interac e-transfer emails."""
    if not all([config.IMAP_HOST, config.IMAP_USER, config.IMAP_PASS]):
        return []
    found: list[int] = []
    try:
        mail = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
        mail.login(config.IMAP_USER, config.IMAP_PASS)
        mail.select("INBOX")
        for term in ['SUBJECT "Interac"', 'SUBJECT "interac"', 'SUBJECT "e-Transfer"', 'SUBJECT "etransfer"']:
            _, msg_ids = mail.search(None, term)
            if not msg_ids[0]:
                continue
            for mid in msg_ids[0].split()[-100:]:
                _, data = mail.fetch(mid, "(RFC822)")
                if not data[0]:
                    continue
                msg = _email_lib.message_from_bytes(data[0][1])
                text = _email_text(msg) + " " + (msg.get("Subject") or "")
                for m in re.finditer(r"LOTTO-(\d+)", text, re.IGNORECASE):
                    dep_id = int(m.group(1))
                    if dep_id not in found:
                        found.append(dep_id)
        mail.close()
        mail.logout()
    except Exception as exc:
        log.warning("IMAP check error: %s", exc)
    return found


async def _check_etransfer_emails(db) -> dict:
    """Check IMAP and auto-approve pending e-transfer deposit requests whose ref code was found."""
    dep_ids = await asyncio.to_thread(_imap_find_lotto_refs)
    approved = 0
    for dep_id in dep_ids:
        cur = await db.execute(
            "SELECT * FROM deposit_requests WHERE id=? AND status='pending' AND payment_method='etransfer'",
            (dep_id,),
        )
        dep = await cur.fetchone()
        if not dep:
            continue
        await db.execute(
            "UPDATE users SET credit=credit+? WHERE telegram_id=?", (dep["amount"], dep["user_id"])
        )
        await db.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (dep["user_id"], "deposit", dep["amount"], f"E-transfer LOTTO-{dep_id}"),
        )
        await db.execute(
            "UPDATE deposit_requests SET status='approved', resolved_at=datetime('now'), "
            "trustee_note='Auto-approved via IMAP' WHERE id=?",
            (dep_id,),
        )
        await db.commit()
        await _notify(
            dep["user_id"],
            f"✅ <b>E-transfer received — ${dep['amount']:.2f}</b>\n"
            f"Your account has been credited. Reference: LOTTO-{dep_id}",
        )
        approved += 1
    return {"checked": len(dep_ids), "approved": approved}


async def _auth(x_init_data: str | None):
    if not x_init_data:
        raise HTTPException(401, "Missing X-Init-Data header")
    db = await get_db()
    user = await _get_user(x_init_data, db)
    return user, db


async def _require_trustee(x_init_data):
    user, db = await _auth(x_init_data)
    if not user["is_trustee"]:
        raise HTTPException(403, "Trustee only")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ptb_app
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url and not config.MINI_APP_URL:
        os.environ["MINI_APP_URL"] = render_url
        config.MINI_APP_URL = render_url
    _ptb_app = build_application()
    await _ptb_app.initialize()
    await _ptb_app.start()
    log.info("PTB started (webhook mode)")
    yield
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
    # Compute lifetime won and spent from transactions
    cur = await db.execute(
        "SELECT type, amount FROM transactions WHERE user_id=?", (user["telegram_id"],)
    )
    txs = await cur.fetchall()
    lifetime_won   = sum(t["amount"] for t in txs if t["type"] == "win")
    lifetime_spent = sum(abs(t["amount"]) for t in txs if t["type"] == "participate")
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
    }


# ---------------------------------------------------------------------------
# /api/round
# ---------------------------------------------------------------------------

@app.get("/api/round")
async def api_round(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute("SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
    round_ = await cur.fetchone()
    if round_ is None:
        cur = await db.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1")
        round_ = await cur.fetchone()
    if round_ is None:
        await db.close()
        return {"round": None}
    rd = dict(round_)
    rd["display_status"] = display_status(rd["status"], rd.get("draw_date"))
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
    my = next((p for p in parts if p["user_id"] == user["telegram_id"]), None)
    rd["participants"] = parts
    rd["pool"] = pool
    rd["my_stake"]  = my["amount"] if my else None
    rd["my_shares"] = round(my["amount"] / (rd.get("price_per_share") or 5)) if my else None
    rd["my_prize"]  = my["prize"]  if my else None
    rd["my_pct"]    = my["pct"]    if my else None
    rd["my_won"]    = my["won"]    if my else None
    rd["pool_target"] = (rd.get("tickets_target") or 25) * (rd.get("price_per_share") or 5)
    rd["has_ticket_image"] = bool(rd.get("ticket_image"))
    rd.pop("ticket_image", None)  # don't send full image in list response
    if rd.get("winner_id"):
        cur = await db.execute(
            "SELECT full_name, username FROM users WHERE telegram_id=?", (rd["winner_id"],)
        )
        w = await cur.fetchone()
        rd["winner_name"] = (w["full_name"] or w["username"]) if w else None
    else:
        rd["winner_name"] = None
    await db.close()
    return {"round": rd}


# ---------------------------------------------------------------------------
# /api/rounds  (NEW)
# ---------------------------------------------------------------------------

@app.get("/api/rounds")
async def api_rounds(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute("""
        SELECT r.*,
          p.amount as my_stake, p.shares as my_shares, p.prize as my_prize,
          (SELECT COUNT(*) FROM participations WHERE round_id=r.id) as participants_count
        FROM rounds r
        LEFT JOIN participations p ON p.round_id=r.id AND p.user_id=?
        ORDER BY r.id DESC LIMIT 20
    """, (user["telegram_id"],))
    rounds = []
    for row in await cur.fetchall():
        rd = dict(row)
        rd["display_status"] = display_status(rd["status"], rd.get("draw_date"))
        rd["pool_target"] = (rd.get("tickets_target") or 25) * (rd.get("price_per_share") or 5)
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
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    cur = await db.execute("SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
    round_ = await cur.fetchone()
    if round_ is None:
        raise HTTPException(400, "No open round")
    if display_status(dict(round_)["status"], dict(round_).get("draw_date")) not in ('OPEN', 'CLOSING'):
        raise HTTPException(400, "Round is not accepting entries right now")
    if user["credit"] < amount:
        raise HTTPException(400, "Insufficient balance")
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
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (user["telegram_id"], "participate", -amount, f"Round #{round_['id']}"),
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
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    await db.execute(
        "INSERT INTO deposit_requests (user_id, amount) VALUES (?,?)",
        (user["telegram_id"], amount),
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

_LOTTERY_SHARE_PRICE = {"lotto_max": 6.0, "649": 3.0, "both": 9.0}


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

@app.get("/api/etransfer/info")
async def etransfer_info(x_init_data: str | None = Header(default=None)):
    await _auth(x_init_data)
    return {
        "enabled": bool(config.ADMIN_ETRANSFER_EMAIL),
        "email": config.ADMIN_ETRANSFER_EMAIL,
    }


@app.post("/api/etransfer/deposit")
async def etransfer_deposit(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    async with db.execute(
        "INSERT INTO deposit_requests (user_id, amount, payment_method) VALUES (?,?,'etransfer') RETURNING id",
        (user["telegram_id"], amount),
    ) as cur:
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
        "admin_email": config.ADMIN_ETRANSFER_EMAIL,
    }


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@app.get("/api/admin/round")
async def admin_round(x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1")
    round_ = await cur.fetchone()
    if round_ is None:
        await db.close()
        return {"round": None}
    rd = dict(round_)
    rd["display_status"] = display_status(rd["status"], rd.get("draw_date"))
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
    rd["participants"] = parts
    rd["pool"] = pool
    rd["pool_target"] = (rd.get("tickets_target") or 25) * (rd.get("price_per_share") or 5)
    rd["has_ticket_image"] = bool(rd.get("ticket_image"))
    if rd.get("ticket_image") and not rd["ticket_image"].startswith("http"):
        rd["ticket_image"] = f"data:image/jpeg;base64,{rd['ticket_image']}"
    await db.close()
    return {"round": rd}


@app.post("/api/admin/round/new")
async def admin_new_round(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    body = await request.json()
    jackpot = body.get("jackpot") or 0
    tickets_target = body.get("tickets_target") or 25
    price_per_share = body.get("price_per_share") or 5.0
    draw_date = body.get("draw_date") or None
    lottery_type = body.get("lottery_type") or "lotto_max"
    async with db.execute(
        "INSERT INTO rounds (status, draw_date, jackpot, tickets_target, price_per_share, lottery_type) VALUES ('open', ?, ?, ?, ?, ?) RETURNING id",
        (draw_date, jackpot, tickets_target, price_per_share, lottery_type)
    ) as cur:
        round_id = cur.lastrowid
    await db.commit()

    # Auto-join eligible users
    await _auto_join_round(db, round_id, price_per_share)

    # Notify all users who want new-round alerts
    draw_str = f" · Draw {draw_date}" if draw_date else ""
    jackpot_str = f" · ${jackpot/1_000_000:.0f}M jackpot" if jackpot else ""
    await _notify_all(db,
        f"🎟 <b>New round opened — #{round_id}</b>{draw_str}{jackpot_str}\n"
        f"${price_per_share:.0f}/share · target {tickets_target} tickets\n"
        f"Open the app to join! 👉",
        setting_col="notif_new_round",
    )

    await db.close()
    return {"ok": True, "round_id": round_id}


@app.post("/api/admin/round/close")
async def admin_close_round(x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute("SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1")
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
    user, db = await _require_trustee(x_init_data)
    body = await request.json()
    round_id = body.get("round_id")
    numbers = body.get("numbers", [])  # list of 7 ints

    if round_id:
        cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_id,))
    else:
        cur = await db.execute("SELECT * FROM rounds WHERE status IN ('open','closed') ORDER BY id DESC LIMIT 1")
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
    user, db = await _require_trustee(x_init_data)

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
        cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_id,))
    else:
        cur = await db.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1")
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
    user, db = await _require_trustee(x_init_data)
    body = await request.json()
    round_id = body.get("round_id")
    winning_numbers = body.get("winning_numbers", [])
    bonus_number = body.get("bonus_number")
    total_prize = float(body.get("total_prize", 0))

    if round_id:
        cur = await db.execute("SELECT * FROM rounds WHERE id=?", (round_id,))
    else:
        cur = await db.execute("SELECT * FROM rounds WHERE status='uploaded' ORDER BY id DESC LIMIT 1")
    round_ = await cur.fetchone()
    if not round_:
        raise HTTPException(400, "No uploaded round found")

    # Get all participations
    cur = await db.execute("SELECT * FROM participations WHERE round_id=?", (round_["id"],))
    parts = await cur.fetchall()
    pool = round_["pool"] or sum(p["amount"] for p in parts)

    # Distribute prize proportionally
    if total_prize > 0 and pool > 0:
        for p in parts:
            share = p["amount"] / pool
            prize = round(share * total_prize, 2)
            await db.execute(
                "UPDATE participations SET prize=? WHERE round_id=? AND user_id=?",
                (prize, round_["id"], p["user_id"])
            )
            if prize > 0:
                await db.execute(
                    "UPDATE users SET credit=credit+? WHERE telegram_id=?", (prize, p["user_id"])
                )
                await db.execute(
                    "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                    (p["user_id"], "win", prize, f"Prize Round #{round_['id']}")
                )

    await db.execute(
        "UPDATE rounds SET status='drawn', winning_numbers=?, bonus_number=?, drawn_at=datetime('now') WHERE id=?",
        (json.dumps(winning_numbers), bonus_number, round_["id"])
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
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute("SELECT * FROM rounds WHERE status IN ('closed','uploaded') ORDER BY id DESC LIMIT 1")
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
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute(
        "SELECT dr.*, u.full_name, u.username FROM deposit_requests dr "
        "JOIN users u ON u.telegram_id=dr.user_id "
        "WHERE dr.status='pending' ORDER BY dr.created_at"
    )
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"deposits": rows, "imap_configured": bool(config.IMAP_HOST)}


@app.post("/api/admin/deposits/{req_id}")
async def admin_resolve_deposit(
    req_id: int, request: Request, x_init_data: str | None = Header(default=None)
):
    user, db = await _require_trustee(x_init_data)
    body = await request.json()
    action = body.get("action")
    cur = await db.execute("SELECT * FROM deposit_requests WHERE id=?", (req_id,))
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
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (dep["user_id"], "deposit", dep["amount"], f"Approved deposit #{req_id}"),
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
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute("SELECT * FROM users ORDER BY created_at")
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"members": rows}


@app.post("/api/admin/etransfer/check")
async def admin_check_etransfer(x_init_data: str | None = Header(default=None)):
    """Manually trigger IMAP check to auto-approve matched e-transfer deposits."""
    user, db = await _require_trustee(x_init_data)
    if not config.IMAP_HOST:
        await db.close()
        raise HTTPException(400, "IMAP not configured (set IMAP_HOST, IMAP_USER, IMAP_PASS)")
    result = await _check_etransfer_emails(db)
    await db.close()
    return result


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
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    charge_amount = round(amount * 1.05, 2)  # 5% processing fee
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
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    charge_amount = round(amount * 1.05, 2)  # 5% processing fee
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
    body = await request.json()
    new_amount = float(body.get("amount", 0))
    if new_amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["telegram_id"],),
    )
    sub_row = await cur.fetchone()
    if sub_row is None:
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
                        stripe_sub["items"]["data"][0]["price"]["unit_amount"] / 100 / 1.05
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
