"""
FastAPI application — serves the REST API, the React Mini App static files,
the Telegram bot webhook, and Stripe payment endpoints.
"""

import hashlib
import hmac
import json
import logging
import os
import random
from contextlib import asynccontextmanager
from datetime import date, datetime
from urllib.parse import parse_qsl

import stripe
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
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

def display_status(status: str, draw_date_str: str | None) -> str:
    if status != "open":
        return "done"
    if not draw_date_str:
        return "live"
    try:
        draw = date.fromisoformat(draw_date_str)
    except ValueError:
        return "live"
    today = date.today()
    if today >= draw or (draw - today).days == 1:
        return "closing"
    return "live"


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
        raise HTTPException(403, "User not registered. Send /start to the bot first.")
    return dict(user)


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
        name=user.get("first_name") or user.get("username") or f"user_{user['telegram_id']}",
    )
    await db.execute(
        "UPDATE users SET stripe_customer_id=? WHERE id=?", (customer.id, user["id"])
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
    await db.close()
    return {**user, "stripe_enabled": bool(config.STRIPE_SECRET_KEY)}


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
    round_dict = dict(round_)
    round_dict["display_status"] = display_status(round_dict["status"], round_dict.get("draw_date"))
    cur = await db.execute(
        "SELECT p.*, u.username, u.first_name FROM participations p "
        "JOIN users u ON u.id=p.user_id WHERE p.round_id=? ORDER BY p.amount DESC",
        (round_dict["id"],),
    )
    parts = [dict(r) for r in await cur.fetchall()]
    total = sum(p["amount"] for p in parts)
    for p in parts:
        p["pct"] = round(p["amount"] / total * 100, 1) if total else 0
        p["won"] = (round_dict.get("winner_id") == p["user_id"])
    winner = None
    if round_dict.get("winner_id"):
        cur = await db.execute("SELECT * FROM users WHERE id=?", (round_dict["winner_id"],))
        w = await cur.fetchone()
        if w:
            winner = dict(w)
    await db.close()
    return {"round": round_dict, "participants": parts, "total": total, "winner": winner}


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
    if display_status(dict(round_)["status"], dict(round_).get("draw_date")) != "live":
        raise HTTPException(400, "Round is not accepting entries right now")
    if user["balance"] < amount:
        raise HTTPException(400, "Insufficient balance")
    try:
        await db.execute(
            "INSERT INTO participations (round_id, user_id, amount) VALUES (?,?,?)",
            (round_["id"], user["id"], amount),
        )
    except Exception:
        raise HTTPException(400, "Already participating in this round")
    await db.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, user["id"]))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (user["id"], "participate", -amount, f"Round #{round_['id']}"),
    )
    await db.commit()
    await db.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# /api/transactions
# ---------------------------------------------------------------------------

@app.get("/api/transactions")
async def api_transactions(x_init_data: str | None = Header(default=None)):
    user, db = await _auth(x_init_data)
    cur = await db.execute(
        "SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 50", (user["id"],)
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
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (user["id"], "deposit_request", amount, "pending approval"),
    )
    await db.commit()
    await db.close()
    return {"ok": True, "message": "Deposit request submitted for approval"}


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
    round_dict = dict(round_)
    round_dict["display_status"] = display_status(round_dict["status"], round_dict.get("draw_date"))
    cur = await db.execute(
        "SELECT p.*, u.username, u.first_name FROM participations p "
        "JOIN users u ON u.id=p.user_id WHERE p.round_id=?",
        (round_dict["id"],),
    )
    parts = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"round": round_dict, "participants": parts}


@app.post("/api/admin/round/new")
async def admin_new_round(request: Request, x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    body = await request.json()
    draw_date = body.get("draw_date") or None
    await db.execute("INSERT INTO rounds (status, draw_date) VALUES ('open', ?)", (draw_date,))
    await db.commit()
    await db.close()
    return {"ok": True}


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
    return {"ok": True}


@app.post("/api/admin/round/draw")
async def admin_draw(x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute("SELECT * FROM rounds WHERE status='closed' ORDER BY id DESC LIMIT 1")
    round_ = await cur.fetchone()
    if round_ is None:
        raise HTTPException(400, "No closed round to draw from")
    cur = await db.execute("SELECT * FROM participations WHERE round_id=?", (round_["id"],))
    parts = await cur.fetchall()
    if not parts:
        raise HTTPException(400, "No participants in this round")
    pool = []
    for p in parts:
        pool.extend([p["user_id"]] * int(p["amount"] * 100))
    winner_id = random.choice(pool)
    total = sum(p["amount"] for p in parts)
    await db.execute(
        "UPDATE rounds SET status='done', winner_id=? WHERE id=?", (winner_id, round_["id"])
    )
    await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (total, winner_id))
    await db.execute(
        "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
        (winner_id, "win", total, f"Won round #{round_['id']}"),
    )
    await db.commit()
    await db.close()
    return {"ok": True, "winner_id": winner_id}


@app.get("/api/admin/deposits")
async def admin_deposits(x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute(
        "SELECT t.*, u.username, u.first_name FROM transactions t "
        "JOIN users u ON u.id=t.user_id WHERE t.type='deposit_request' ORDER BY t.id DESC"
    )
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"deposits": rows}


@app.post("/api/admin/deposits/{tx_id}")
async def admin_resolve_deposit(
    tx_id: int, request: Request, x_init_data: str | None = Header(default=None)
):
    user, db = await _require_trustee(x_init_data)
    body = await request.json()
    action = body.get("action")
    cur = await db.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
    tx = await cur.fetchone()
    if tx is None:
        raise HTTPException(404, "Transaction not found")
    if tx["type"] != "deposit_request":
        raise HTTPException(400, "Not a deposit request")
    if action == "approve":
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (tx["amount"], tx["user_id"]))
        await db.execute(
            "UPDATE transactions SET type='deposit', note='approved' WHERE id=?", (tx_id,)
        )
    elif action == "reject":
        await db.execute(
            "UPDATE transactions SET type='deposit_rejected', note='rejected' WHERE id=?", (tx_id,)
        )
    else:
        raise HTTPException(400, "action must be approve or reject")
    await db.commit()
    await db.close()
    return {"ok": True}


@app.get("/api/admin/members")
async def admin_members(x_init_data: str | None = Header(default=None)):
    user, db = await _require_trustee(x_init_data)
    cur = await db.execute("SELECT * FROM users ORDER BY id")
    rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return {"members": rows}


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
    try:
        customer_id = await _get_or_create_customer(user, db)
        pi = stripe.PaymentIntent.create(
            amount=int(amount * 100),
            currency=config.CURRENCY.lower(),
            customer=customer_id,
            automatic_payment_methods={"enabled": True},
            metadata={"user_id": str(user["id"]), "telegram_id": str(user["telegram_id"])},
        )
        await db.close()
        return {"client_secret": pi.client_secret}
    except stripe.StripeError as e:
        await db.close()
        raise HTTPException(400, str(e.user_message or e))
    except Exception as e:
        await db.close()
        log.exception("payment-intent error")
        raise HTTPException(500, "Payment setup failed")


@app.post("/api/stripe/subscription/create")
async def stripe_create_subscription(
    request: Request, x_init_data: str | None = Header(default=None)
):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["id"],),
    )
    if await cur.fetchone():
        raise HTTPException(400, "Already have an active subscription")
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    try:
        customer_id = await _get_or_create_customer(user, db)
        price = stripe.Price.create(
            unit_amount=int(amount * 100),
            currency=config.CURRENCY.lower(),
            recurring={"interval": "month"},
            product_data={"name": "Lottoomax Monthly Deposit"},
        )
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{"price": price.id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            expand=["latest_invoice.payment_intent"],
            metadata={"user_id": str(user["id"]), "telegram_id": str(user["telegram_id"])},
        )
        client_secret = subscription.latest_invoice.payment_intent.client_secret
        await db.close()
        return {"client_secret": client_secret, "subscription_id": subscription.id}
    except stripe.StripeError as e:
        await db.close()
        raise HTTPException(400, str(e.user_message or e))
    except Exception as e:
        await db.close()
        log.exception("subscription/create error")
        raise HTTPException(500, "Subscription setup failed")


@app.get("/api/stripe/subscription")
async def stripe_get_subscription(x_init_data: str | None = Header(default=None)):
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(400, "Stripe not configured")
    user, db = await _auth(x_init_data)
    cur = await db.execute(
        "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' LIMIT 1",
        (user["id"],),
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
        (user["id"],),
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
        (user["id"],),
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
            amount = pi["amount_received"] / 100
            await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id))
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
        if sub_row is None:
            # First payment — store the subscription record
            try:
                stripe_sub = stripe.Subscription.retrieve(sub_id)
                user_id = int(stripe_sub.metadata.get("user_id", 0))
                if user_id:
                    amt_cents = stripe_sub["items"]["data"][0]["price"]["unit_amount"]
                    await db.execute(
                        "INSERT OR IGNORE INTO stripe_subscriptions "
                        "(user_id, stripe_sub_id, amount, status) VALUES (?,?,?,'active')",
                        (user_id, sub_id, amt_cents / 100),
                    )
            except Exception as exc:
                log.error("Failed to store subscription: %s", exc)
        else:
            user_id = sub_row["user_id"]
        if user_id:
            amount = invoice.get("amount_paid", 0) / 100
            if amount > 0:
                await db.execute(
                    "UPDATE users SET balance=balance+? WHERE id=?", (amount, user_id)
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
    return _CLOSE_PAGE.format(title="Success", icon="\u2705", msg="Payment successful! Closing\u2026")


@app.get("/payment-cancel", response_class=HTMLResponse)
async def payment_cancel():
    return _CLOSE_PAGE.format(title="Cancelled", icon="\u274c", msg="Payment cancelled. Closing\u2026")


# ---------------------------------------------------------------------------
# Static files — must be last
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="mini_app/dist", html=True), name="static")
