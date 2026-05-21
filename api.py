"""
FastAPI: Mini App API + Telegram webhook + Stripe payments.
"""

from __future__ import annotations

import hashlib, hmac, json, logging, os, random
from contextlib import asynccontextmanager
from datetime import date as _date, datetime
from pathlib import Path
from urllib.parse import parse_qsl

import aiosqlite
import stripe as _stripe
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler

load_dotenv()
log = logging.getLogger(__name__)

BOT_TOKEN             = os.getenv("BOT_TOKEN", "")
TRUSTEE_ID            = int(os.getenv("TRUSTEE_TELEGRAM_ID", "0"))
DB_PATH               = os.getenv("DB_PATH", "lotto.db")
CURRENCY              = os.getenv("CURRENCY", "CAD")
_render_url           = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_URL           = os.getenv("WEBHOOK_URL", _render_url)
STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STATIC_DIR            = Path(__file__).parent / "mini_app" / "dist"

if STRIPE_SECRET_KEY:
    _stripe.api_key = STRIPE_SECRET_KEY

_ptb: Application | None = None


# ── Display status ────────────────────────────────────────────────────────────

def display_status(status: str, draw_date_str) -> str:
    if status == "drawn":
        return "done"
    if status == "closed":
        return "closing"
    if not draw_date_str:
        return "live"
    try:
        days = (_date.fromisoformat(draw_date_str) - _date.today()).days
        return "live" if days > 1 else "closing" if days >= 0 else "done"
    except Exception:
        return "live"


# ── Bot setup ─────────────────────────────────────────────────────────────────

def _setup_ptb() -> Application:
    import database as _db
    from handlers.start   import cmd_start, cmd_menu
    from handlers.credit  import (show_balance, show_transactions,
                                   handle_deposit_decision, build_deposit_conversation)
    from handlers.lottery import (show_round, show_my_tickets, show_history,
                                   show_invite, build_participate_conversation)
    from handlers.admin   import (cmd_newround, cmd_closeround, cmd_roundinfo,
                                   cmd_deposits, cmd_members, build_draw_conversation)
    from bot import callback_router

    ptb = ApplicationBuilder().token(BOT_TOKEN).updater(None).build()
    ptb.add_handler(build_deposit_conversation())
    ptb.add_handler(build_participate_conversation())
    ptb.add_handler(build_draw_conversation())
    for cmd, fn in [("start", cmd_start), ("menu", cmd_menu), ("balance", show_balance),
                    ("round", show_round), ("tickets", show_my_tickets), ("history", show_history),
                    ("invite", show_invite), ("transactions", show_transactions),
                    ("newround", cmd_newround), ("closeround", cmd_closeround),
                    ("roundinfo", cmd_roundinfo), ("deposits", cmd_deposits), ("members", cmd_members)]:
        ptb.add_handler(CommandHandler(cmd, fn))
    ptb.add_handler(CallbackQueryHandler(callback_router))
    return ptb


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    global _ptb
    if BOT_TOKEN:
        import database as _db
        _ptb = _setup_ptb()
        _ptb.bot_data["db"] = await _db.get_db()
        await _ptb.initialize()
        await _ptb.start()
        if WEBHOOK_URL and not os.getenv("MINI_APP_URL"):
            os.environ["MINI_APP_URL"] = WEBHOOK_URL
        if WEBHOOK_URL:
            await _ptb.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram-webhook",
                                        allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    yield
    if _ptb:
        if WEBHOOK_URL:
            await _ptb.bot.delete_webhook()
        await _ptb.stop()
        await _ptb.shutdown()


app = FastAPI(title="Lottoomax API", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Telegram webhook ──────────────────────────────────────────────────────────

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    if _ptb is None:
        raise HTTPException(503, "Bot not initialised")
    await _ptb.process_update(Update.de_json(await request.json(), _ptb.bot))
    return {"ok": True}


# ── DB / Auth ─────────────────────────────────────────────────────────────────

async def open_db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    return conn

def _parse_init_data(raw: str) -> dict:
    pairs    = dict(parse_qsl(raw, keep_blank_values=True))
    received = pairs.pop("hash", "")
    check    = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret   = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received):
        raise HTTPException(401, "Invalid Telegram initData")
    return json.loads(pairs["user"])

async def current_user(x_init_data: str = Header(..., alias="X-Init-Data")) -> dict:
    return _parse_init_data(x_init_data)

async def trustee_only(user: dict = Depends(current_user)) -> dict:
    if user["id"] != TRUSTEE_ID:
        raise HTTPException(403, "Trustee only")
    return user


# ── /api/me ───────────────────────────────────────────────────────────────────

@app.get("/api/me")
async def me(user: dict = Depends(current_user)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM users WHERE telegram_id=?", (user["id"],)) as c:
            row = await c.fetchone()
        if not row:
            raise HTTPException(404, "Not registered — open @Lottoomax_bot first")
        return {"id": row["telegram_id"], "full_name": row["full_name"],
                "username": row["username"], "credit": row["credit"],
                "is_trustee": bool(row["is_trustee"]),
                "stripe_enabled": bool(STRIPE_SECRET_KEY)}
    finally:
        await conn.close()


# ── /api/deposit (manual request) ────────────────────────────────────────────

class DepositIn(BaseModel):
    amount: float

@app.post("/api/deposit")
async def request_deposit(body: DepositIn, user: dict = Depends(current_user)):
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    conn = await open_db()
    try:
        async with conn.execute("SELECT 1 FROM users WHERE telegram_id=?", (user["id"],)) as c:
            if not await c.fetchone():
                raise HTTPException(404, "Not registered")
        async with conn.execute(
            "INSERT INTO deposit_requests (user_id, amount) VALUES (?,?)", (user["id"], body.amount)
        ) as c:
            req_id = c.lastrowid
        await conn.commit()
        return {"id": req_id, "status": "pending", "amount": body.amount}
    finally:
        await conn.close()


# ── /api/round ────────────────────────────────────────────────────────────────

async def _build_round_payload(conn, row, user_id):
    rid, pool, status = row["id"], row["pool"], row["status"]
    dd = row["draw_date"] if row["draw_date"] else None
    ds = display_status(status, dd)

    async with conn.execute(
        """SELECT p.user_id, p.amount, u.full_name
           FROM participations p JOIN users u ON u.telegram_id=p.user_id
           WHERE p.round_id=? ORDER BY p.amount DESC""", (rid,)
    ) as c:
        parts = await c.fetchall()

    winner_name = None
    if row["winner_id"]:
        async with conn.execute("SELECT full_name FROM users WHERE telegram_id=?", (row["winner_id"],)) as c:
            w = await c.fetchone()
            winner_name = w["full_name"] if w else "Unknown"

    async with conn.execute("SELECT amount FROM participations WHERE round_id=? AND user_id=?", (rid, user_id)) as c:
        own = await c.fetchone()

    my_stake = own["amount"] if own else None
    return {
        "id": rid, "status": status, "display_status": ds, "pool": pool,
        "draw_date": dd, "drawn_at": row["drawn_at"],
        "winner_id": row["winner_id"], "winner_name": winner_name,
        "participants": [{"user_id": p["user_id"], "full_name": p["full_name"],
                          "amount": p["amount"],
                          "pct": round(p["amount"] / pool * 100, 1) if pool else 0,
                          "won": p["user_id"] == row["winner_id"]} for p in parts],
        "my_stake": my_stake,
        "my_pct": round(my_stake / pool * 100, 1) if (my_stake and pool) else None,
        "my_won": row["winner_id"] == user_id if row["winner_id"] else None,
    }

@app.get("/api/round")
async def get_round(user: dict = Depends(current_user)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1") as c:
            row = await c.fetchone()
        if not row:
            async with conn.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1") as c:
                row = await c.fetchone()
        if not row:
            return {"round": None}
        return {"round": await _build_round_payload(conn, row, user["id"])}
    finally:
        await conn.close()

class StakeIn(BaseModel):
    amount: float

@app.post("/api/participate")
async def participate(body: StakeIn, user: dict = Depends(current_user)):
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    conn = await open_db()
    try:
        async with conn.execute("SELECT credit FROM users WHERE telegram_id=?", (user["id"],)) as c:
            row = await c.fetchone()
        if not row:
            raise HTTPException(404, "Not registered")
        if row["credit"] < body.amount:
            raise HTTPException(400, f"Insufficient balance ({row['credit']:.2f} {CURRENCY})")
        async with conn.execute("SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1") as c:
            round_ = await c.fetchone()
        if not round_:
            raise HTTPException(400, "No open round")
        if display_status(round_["status"], round_["draw_date"]) != "live":
            raise HTTPException(400, "Participation is closed — the draw is imminent")
        rid = round_["id"]
        async with conn.execute("SELECT id FROM participations WHERE round_id=? AND user_id=?", (rid, user["id"])) as c:
            existing = await c.fetchone()
        if existing:
            await conn.execute("UPDATE participations SET amount=amount+? WHERE round_id=? AND user_id=?",
                               (body.amount, rid, user["id"]))
        else:
            await conn.execute("INSERT INTO participations (round_id, user_id, amount) VALUES (?,?,?)",
                               (rid, user["id"], body.amount))
        await conn.execute("UPDATE rounds SET pool=pool+? WHERE id=?", (body.amount, rid))
        await conn.execute("UPDATE users SET credit=credit-? WHERE telegram_id=?", (body.amount, user["id"]))
        await conn.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                           (user["id"], "participate", body.amount, f"Round #{rid} stake"))
        await conn.commit()
        async with conn.execute("SELECT pool FROM rounds WHERE id=?", (rid,)) as c:
            updated = await c.fetchone()
        async with conn.execute("SELECT amount FROM participations WHERE round_id=? AND user_id=?", (rid, user["id"])) as c:
            own = await c.fetchone()
        new_pool, stake = updated["pool"], own["amount"]
        return {"pool": new_pool, "my_stake": stake,
                "my_pct": round(stake / new_pool * 100, 1) if new_pool else 0}
    finally:
        await conn.close()


# ── /api/transactions ─────────────────────────────────────────────────────────

@app.get("/api/transactions")
async def transactions(user: dict = Depends(current_user)):
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 40", (user["id"],)
        ) as c:
            rows = await c.fetchall()
        return {"transactions": [{"id": r["id"], "type": r["type"], "amount": r["amount"],
                                   "note": r["note"], "created_at": r["created_at"]} for r in rows]}
    finally:
        await conn.close()


# ── Admin ─────────────────────────────────────────────────────────────────────

class NewRoundIn(BaseModel):
    draw_date: str | None = None

@app.post("/api/admin/round/new")
async def admin_new_round(body: NewRoundIn = NewRoundIn(), _: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT id FROM rounds WHERE status='open' LIMIT 1") as c:
            if await c.fetchone():
                raise HTTPException(400, "A round is already open")
        async with conn.execute("INSERT INTO rounds (status, draw_date) VALUES ('open', ?)", (body.draw_date,)) as c:
            rid = c.lastrowid
        await conn.commit()
        return {"round_id": rid}
    finally:
        await conn.close()

@app.post("/api/admin/round/close")
async def admin_close_round(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT id FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1") as c:
            row = await c.fetchone()
        if not row:
            raise HTTPException(400, "No open round to close")
        await conn.execute("UPDATE rounds SET status='closed', closed_at=datetime('now') WHERE id=?", (row["id"],))
        await conn.commit()
        return {"round_id": row["id"], "status": "closed"}
    finally:
        await conn.close()

@app.post("/api/admin/round/draw")
async def admin_draw(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM rounds WHERE status='closed' ORDER BY id DESC LIMIT 1") as c:
            round_ = await c.fetchone()
        if not round_:
            raise HTTPException(400, "No closed round to draw")
        rid, pool = round_["id"], round_["pool"]
        async with conn.execute(
            "SELECT p.user_id, p.amount, u.full_name FROM participations p "
            "JOIN users u ON u.telegram_id=p.user_id WHERE p.round_id=?", (rid,)
        ) as c:
            parts = await c.fetchall()
        if not parts:
            raise HTTPException(400, "No participants")
        winner_id = random.choices([p["user_id"] for p in parts], weights=[p["amount"] for p in parts], k=1)[0]
        winner = next(p for p in parts if p["user_id"] == winner_id)
        pct = round(winner["amount"] / pool * 100, 1) if pool else 0
        await conn.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (pool, winner_id))
        await conn.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                           (winner_id, "win", pool, f"Round #{rid} prize"))
        await conn.execute("UPDATE rounds SET status='drawn', winner_id=?, drawn_at=datetime('now') WHERE id=?",
                           (winner_id, rid))
        await conn.commit()
        return {"round_id": rid, "winner_id": winner_id,
                "winner_name": winner["full_name"], "pool": pool, "winner_pct": pct}
    finally:
        await conn.close()

@app.get("/api/admin/round")
async def admin_round_info(_u: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 1") as c:
            row = await c.fetchone()
        if not row:
            return {"round": None}
        rid, pool = row["id"], row["pool"]
        async with conn.execute(
            "SELECT p.user_id, p.amount, u.full_name FROM participations p "
            "JOIN users u ON u.telegram_id=p.user_id WHERE p.round_id=? ORDER BY p.amount DESC", (rid,)
        ) as c:
            parts = await c.fetchall()
        return {"round": {"id": rid, "status": row["status"],
                          "display_status": display_status(row["status"], row["draw_date"]),
                          "pool": pool, "draw_date": row["draw_date"],
                          "opened_at": row["opened_at"], "closed_at": row["closed_at"],
                          "drawn_at": row["drawn_at"], "winner_id": row["winner_id"],
                          "participants": [{"user_id": p["user_id"], "full_name": p["full_name"],
                                            "amount": p["amount"],
                                            "pct": round(p["amount"] / pool * 100, 1) if pool else 0,
                                            "won": p["user_id"] == row["winner_id"]} for p in parts]}}
    finally:
        await conn.close()

@app.get("/api/admin/deposits")
async def admin_deposits(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT dr.*, u.full_name, u.username FROM deposit_requests dr "
            "JOIN users u ON u.telegram_id=dr.user_id WHERE dr.status='pending' ORDER BY dr.created_at"
        ) as c:
            rows = await c.fetchall()
        return {"deposits": [{"id": r["id"], "user_id": r["user_id"], "full_name": r["full_name"],
                               "username": r["username"], "amount": r["amount"],
                               "created_at": r["created_at"]} for r in rows]}
    finally:
        await conn.close()

class ResolveIn(BaseModel):
    action: str
    note: str | None = None

@app.post("/api/admin/deposits/{req_id}")
async def admin_resolve(req_id: int, body: ResolveIn, _: dict = Depends(trustee_only)):
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM deposit_requests WHERE id=?", (req_id,)) as c:
            req = await c.fetchone()
        if not req:
            raise HTTPException(404, "Not found")
        if req["status"] != "pending":
            raise HTTPException(400, "Already resolved")
        status = "approved" if body.action == "approve" else "rejected"
        await conn.execute(
            "UPDATE deposit_requests SET status=?, trustee_note=?, resolved_at=datetime('now') WHERE id=?",
            (status, body.note, req_id))
        if status == "approved":
            await conn.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (req["amount"], req["user_id"]))
            await conn.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                               (req["user_id"], "deposit", req["amount"], f"Deposit #{req_id} approved"))
        await conn.commit()
        return {"status": status}
    finally:
        await conn.close()

@app.get("/api/admin/members")
async def admin_members(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM users ORDER BY created_at") as c:
            rows = await c.fetchall()
        return {"members": [{"telegram_id": r["telegram_id"], "full_name": r["full_name"],
                              "username": r["username"], "credit": r["credit"],
                              "is_trustee": bool(r["is_trustee"]), "created_at": r["created_at"]}
                             for r in rows]}
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# STRIPE
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_or_create_customer(conn, telegram_id: int, full_name: str) -> str:
    async with conn.execute("SELECT stripe_customer_id FROM users WHERE telegram_id=?", (telegram_id,)) as c:
        row = await c.fetchone()
    cid = row["stripe_customer_id"] if row else None
    if not cid:
        customer = _stripe.Customer.create(name=full_name, metadata={"telegram_id": str(telegram_id)})
        cid = customer.id
        await conn.execute("UPDATE users SET stripe_customer_id=? WHERE telegram_id=?", (cid, telegram_id))
        await conn.commit()
    return cid


class CheckoutIn(BaseModel):
    amount: float
    type: str   # "one_time" | "subscription"


@app.post("/api/stripe/checkout")
async def stripe_checkout(body: CheckoutIn, user: dict = Depends(current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe not configured")
    if body.amount < 1:
        raise HTTPException(400, "Minimum amount is 1 CAD")
    if body.type not in ("one_time", "subscription"):
        raise HTTPException(400, "type must be one_time or subscription")

    conn = await open_db()
    try:
        async with conn.execute("SELECT * FROM users WHERE telegram_id=?", (user["id"],)) as c:
            u = await c.fetchone()
        if not u:
            raise HTTPException(404, "Not registered")

        cid      = await _get_or_create_customer(conn, user["id"], u["full_name"])
        base     = (WEBHOOK_URL or "http://localhost:8000").rstrip("/")
        unit_amt = int(round(body.amount * 100))

        if body.type == "one_time":
            session = _stripe.checkout.Session.create(
                customer=cid,
                mode="payment",
                line_items=[{"price_data": {"currency": "cad", "unit_amount": unit_amt,
                              "product_data": {"name": "Lottoomax Deposit"}}, "quantity": 1}],
                success_url=f"{base}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base}/payment-cancel",
                metadata={"telegram_id": str(user["id"]), "type": "one_time"},
            )
        else:
            # Block if active subscription already exists
            async with conn.execute(
                "SELECT id FROM stripe_subscriptions WHERE user_id=? AND status='active'", (user["id"],)
            ) as c:
                if await c.fetchone():
                    raise HTTPException(400, "You already have an active subscription — update the amount instead.")

            session = _stripe.checkout.Session.create(
                customer=cid,
                mode="subscription",
                line_items=[{"price_data": {"currency": "cad", "unit_amount": unit_amt,
                              "recurring": {"interval": "month"},
                              "product_data": {"name": "Lottoomax Monthly Deposit"}}, "quantity": 1}],
                success_url=f"{base}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base}/payment-cancel",
                metadata={"telegram_id": str(user["id"]), "type": "subscription"},
            )

        return {"checkout_url": session.url}
    finally:
        await conn.close()


@app.get("/api/stripe/subscription")
async def get_stripe_subscription(user: dict = Depends(current_user)):
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status IN ('active','cancelling') "
            "ORDER BY id DESC LIMIT 1", (user["id"],)
        ) as c:
            row = await c.fetchone()
        if not row:
            return {"subscription": None}
        next_billing = None
        try:
            sub = _stripe.Subscription.retrieve(row["stripe_sub_id"])
            next_billing = datetime.utcfromtimestamp(sub["current_period_end"]).strftime("%Y-%m-%d")
        except Exception:
            pass
        return {"subscription": {"id": row["stripe_sub_id"], "amount": row["amount"],
                                  "status": row["status"], "next_billing": next_billing}}
    finally:
        await conn.close()


class UpdateSubIn(BaseModel):
    amount: float

@app.post("/api/stripe/subscription/update")
async def update_stripe_subscription(body: UpdateSubIn, user: dict = Depends(current_user)):
    if body.amount < 1:
        raise HTTPException(400, "Minimum amount is 1 CAD")
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT * FROM stripe_subscriptions WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (user["id"],)
        ) as c:
            row = await c.fetchone()
        if not row:
            raise HTTPException(404, "No active subscription")

        sub    = _stripe.Subscription.retrieve(row["stripe_sub_id"])
        item   = sub["items"]["data"][0]
        prod   = item["price"]["product"]
        price  = _stripe.Price.create(unit_amount=int(round(body.amount * 100)),
                                       currency="cad", recurring={"interval": "month"}, product=prod)
        _stripe.Subscription.modify(row["stripe_sub_id"],
                                     items=[{"id": item["id"], "price": price.id}],
                                     proration_behavior="none")
        await conn.execute("UPDATE stripe_subscriptions SET amount=?, updated_at=datetime('now') WHERE stripe_sub_id=?",
                           (body.amount, row["stripe_sub_id"]))
        await conn.commit()
        return {"amount": body.amount}
    finally:
        await conn.close()


@app.post("/api/stripe/subscription/cancel")
async def cancel_stripe_subscription(user: dict = Depends(current_user)):
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT stripe_sub_id FROM stripe_subscriptions WHERE user_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (user["id"],)
        ) as c:
            row = await c.fetchone()
        if not row:
            raise HTTPException(404, "No active subscription")
        _stripe.Subscription.modify(row["stripe_sub_id"], cancel_at_period_end=True)
        await conn.execute("UPDATE stripe_subscriptions SET status='cancelling', updated_at=datetime('now') WHERE stripe_sub_id=?",
                           (row["stripe_sub_id"],))
        await conn.commit()
        return {"status": "cancelling"}
    finally:
        await conn.close()


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook secret not set")
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")
    try:
        event = _stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(400, str(e))

    conn = await open_db()
    try:
        etype = event["type"]
        obj   = event["data"]["object"]

        if etype == "checkout.session.completed":
            telegram_id = int(obj["metadata"].get("telegram_id", 0))
            pay_type    = obj["metadata"].get("type", "")
            if not telegram_id:
                return {"ok": True}

            if pay_type == "one_time" and obj["mode"] == "payment":
                amount = (obj.get("amount_total") or 0) / 100
                if amount > 0:
                    await conn.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (amount, telegram_id))
                    await conn.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                                       (telegram_id, "deposit", amount, "Stripe one-time payment"))
                    await conn.commit()

            elif pay_type == "subscription" and obj["mode"] == "subscription":
                stripe_sub_id = obj.get("subscription")
                if stripe_sub_id:
                    sub    = _stripe.Subscription.retrieve(stripe_sub_id)
                    amount = sub["items"]["data"][0]["price"]["unit_amount"] / 100
                    await conn.execute(
                        "INSERT OR IGNORE INTO stripe_subscriptions (user_id, stripe_sub_id, amount) VALUES (?,?,?)",
                        (telegram_id, stripe_sub_id, amount))
                    await conn.commit()

        elif etype == "invoice.payment_succeeded":
            sub_id = obj.get("subscription")
            if not sub_id:
                return {"ok": True}   # one-time invoice, already handled above
            customer_id = obj.get("customer")
            async with conn.execute("SELECT telegram_id FROM users WHERE stripe_customer_id=?", (customer_id,)) as c:
                u = await c.fetchone()
            if not u:
                return {"ok": True}
            amount = (obj.get("amount_paid") or 0) / 100
            if amount > 0:
                await conn.execute("UPDATE users SET credit=credit+? WHERE telegram_id=?", (amount, u["telegram_id"]))
                await conn.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                                   (u["telegram_id"], "deposit", amount, "Stripe monthly subscription"))
                await conn.commit()

        elif etype == "customer.subscription.deleted":
            await conn.execute("UPDATE stripe_subscriptions SET status='cancelled', updated_at=datetime('now') WHERE stripe_sub_id=?",
                               (obj["id"],))
            await conn.commit()

        return {"ok": True}
    finally:
        await conn.close()


# ── Payment result pages ──────────────────────────────────────────────────────

@app.get("/payment-success")
async def payment_success():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Payment Successful</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       text-align:center;padding:64px 24px;background:#f9f9f9;color:#1a1a1a;}
  .icon{font-size:72px;margin-bottom:16px;}
  h1{color:#2e7d32;font-size:24px;margin-bottom:8px;}
  p{color:#666;font-size:16px;line-height:1.5;}
  .note{margin-top:24px;font-size:13px;color:#999;}
</style></head>
<body>
  <div class="icon">&#x2705;</div>
  <h1>Payment Successful!</h1>
  <p>Your balance has been credited.<br>Return to Telegram to continue.</p>
  <p class="note">This tab will close automatically&#x2026;</p>
  <script>setTimeout(()=>{try{window.close()}catch(e){}},3500)</script>
</body></html>""")

@app.get("/payment-cancel")
async def payment_cancel():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Payment Cancelled</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       text-align:center;padding:64px 24px;background:#f9f9f9;color:#1a1a1a;}
  .icon{font-size:72px;margin-bottom:16px;}
  h1{color:#c62828;font-size:24px;margin-bottom:8px;}
  p{color:#666;font-size:16px;line-height:1.5;}
</style></head>
<body>
  <div class="icon">&#x274C;</div>
  <h1>Payment Cancelled</h1>
  <p>No charge was made.<br>Return to Telegram to try again.</p>
  <script>setTimeout(()=>{try{window.close()}catch(e){}},3000)</script>
</body></html>""")


# ── Static files ──────────────────────────────────────────────────────────────

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
