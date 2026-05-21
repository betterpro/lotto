"""
FastAPI app: Mini App REST API + Telegram webhook in one process.
RENDER_EXTERNAL_URL is injected automatically by Render.
"""

from __future__ import annotations

import hashlib, hmac, json, logging, os, random
from contextlib import asynccontextmanager
from datetime import date as _date
from pathlib import Path
from urllib.parse import parse_qsl

import aiosqlite
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler

load_dotenv()
log = logging.getLogger(__name__)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
TRUSTEE_ID  = int(os.getenv("TRUSTEE_TELEGRAM_ID", "0"))
DB_PATH     = os.getenv("DB_PATH", "lotto.db")
CURRENCY    = os.getenv("CURRENCY", "CAD")
_render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", _render_url)
STATIC_DIR  = Path(__file__).parent / "mini_app" / "dist"

_ptb: Application | None = None


# ── Display status helper ─────────────────────────────────────────────────────

def display_status(status: str, draw_date_str) -> str:
    """
    Compute UI status from DB status + draw_date.
      live    -> green  (> 1 day until draw)
      closing -> yellow (<= 1 day until draw, or round closed)
      done    -> red    (drawn, or past draw date)
    """
    if status == "drawn":
        return "done"
    if status == "closed":
        return "closing"
    # status == "open"
    if not draw_date_str:
        return "live"
    try:
        days = (_date.fromisoformat(draw_date_str) - _date.today()).days
        if days > 1:
            return "live"
        elif days >= 0:
            return "closing"
        else:
            return "done"
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
    ptb.add_handler(CommandHandler("start",        cmd_start))
    ptb.add_handler(CommandHandler("menu",         cmd_menu))
    ptb.add_handler(CommandHandler("balance",      show_balance))
    ptb.add_handler(CommandHandler("round",        show_round))
    ptb.add_handler(CommandHandler("tickets",      show_my_tickets))
    ptb.add_handler(CommandHandler("history",      show_history))
    ptb.add_handler(CommandHandler("invite",       show_invite))
    ptb.add_handler(CommandHandler("transactions", show_transactions))
    ptb.add_handler(CommandHandler("newround",     cmd_newround))
    ptb.add_handler(CommandHandler("closeround",   cmd_closeround))
    ptb.add_handler(CommandHandler("roundinfo",    cmd_roundinfo))
    ptb.add_handler(CommandHandler("deposits",     cmd_deposits))
    ptb.add_handler(CommandHandler("members",      cmd_members))
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
            await _ptb.bot.set_webhook(
                url=f"{WEBHOOK_URL}/telegram-webhook",
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True)
            log.info("Webhook: %s/telegram-webhook", WEBHOOK_URL)
    yield
    if _ptb:
        if WEBHOOK_URL:
            await _ptb.bot.delete_webhook()
        await _ptb.stop()
        await _ptb.shutdown()


app = FastAPI(title="Lottoomax API", docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    if _ptb is None:
        raise HTTPException(503, "Bot not initialised")
    update = Update.de_json(await request.json(), _ptb.bot)
    await _ptb.process_update(update)
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
                "is_trustee": bool(row["is_trustee"])}
    finally:
        await conn.close()


# ── /api/deposit ──────────────────────────────────────────────────────────────

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


# ── /api/round  (latest round with display_status + winner info) ───────────────

async def _build_round_payload(conn, row, user_id):
    """Build the full round dict including participants and display status."""
    rid      = row["id"]
    pool     = row["pool"]
    status   = row["status"]
    dd       = row["draw_date"] if row["draw_date"] else None
    ds       = display_status(status, dd)

    async with conn.execute(
        """SELECT p.user_id, p.amount, u.full_name
           FROM participations p JOIN users u ON u.telegram_id=p.user_id
           WHERE p.round_id=? ORDER BY p.amount DESC""", (rid,)
    ) as c:
        parts = await c.fetchall()

    # Winner name for done rounds
    winner_name = None
    if row["winner_id"]:
        async with conn.execute(
            "SELECT full_name FROM users WHERE telegram_id=?", (row["winner_id"],)
        ) as c:
            w = await c.fetchone()
            winner_name = w["full_name"] if w else "Unknown"

    async with conn.execute(
        "SELECT amount FROM participations WHERE round_id=? AND user_id=?", (rid, user_id)
    ) as c:
        own = await c.fetchone()

    participants = []
    for p in parts:
        participants.append({
            "user_id":    p["user_id"],
            "full_name":  p["full_name"],
            "amount":     p["amount"],
            "pct":        round(p["amount"] / pool * 100, 1) if pool else 0,
            "won":        p["user_id"] == row["winner_id"],
        })

    my_stake = own["amount"] if own else None
    return {
        "id":           rid,
        "status":       status,
        "display_status": ds,
        "pool":         pool,
        "draw_date":    dd,
        "drawn_at":     row["drawn_at"],
        "winner_id":    row["winner_id"],
        "winner_name":  winner_name,
        "participants": participants,
        "my_stake":     my_stake,
        "my_pct":       round(my_stake / pool * 100, 1) if (my_stake and pool) else None,
        "my_won":       row["winner_id"] == user_id if row["winner_id"] else None,
    }


@app.get("/api/round")
async def get_round(user: dict = Depends(current_user)):
    conn = await open_db()
    try:
        # Prefer open round; fall back to most recent
        async with conn.execute(
            "SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1"
        ) as c:
            row = await c.fetchone()
        if not row:
            async with conn.execute(
                "SELECT * FROM rounds ORDER BY id DESC LIMIT 1"
            ) as c:
                row = await c.fetchone()
        if not row:
            return {"round": None}
        return {"round": await _build_round_payload(conn, row, user["id"])}
    finally:
        await conn.close()


# ── /api/participate ──────────────────────────────────────────────────────────

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

        async with conn.execute(
            "SELECT * FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1"
        ) as c:
            round_ = await c.fetchone()
        if not round_:
            raise HTTPException(400, "No open round")

        # Block participation if round is closing or done based on draw_date
        ds = display_status(round_["status"], round_["draw_date"])
        if ds != "live":
            raise HTTPException(400, "Participation is closed — the draw is imminent")

        rid = round_["id"]
        async with conn.execute(
            "SELECT id FROM participations WHERE round_id=? AND user_id=?", (rid, user["id"])
        ) as c:
            existing = await c.fetchone()
        if existing:
            await conn.execute(
                "UPDATE participations SET amount=amount+? WHERE round_id=? AND user_id=?",
                (body.amount, rid, user["id"]))
        else:
            await conn.execute(
                "INSERT INTO participations (round_id, user_id, amount) VALUES (?,?,?)",
                (rid, user["id"], body.amount))
        await conn.execute("UPDATE rounds SET pool=pool+? WHERE id=?", (body.amount, rid))
        await conn.execute(
            "UPDATE users SET credit=credit-? WHERE telegram_id=?", (body.amount, user["id"]))
        await conn.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (user["id"], "participate", body.amount, f"Round #{rid} stake"))
        await conn.commit()

        async with conn.execute("SELECT pool FROM rounds WHERE id=?", (rid,)) as c:
            updated = await c.fetchone()
        async with conn.execute(
            "SELECT amount FROM participations WHERE round_id=? AND user_id=?", (rid, user["id"])
        ) as c:
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
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 40",
            (user["id"],)
        ) as c:
            rows = await c.fetchall()
        return {"transactions": [{"id": r["id"], "type": r["type"], "amount": r["amount"],
                                   "note": r["note"], "created_at": r["created_at"]}
                                  for r in rows]}
    finally:
        await conn.close()


# ── Admin ─────────────────────────────────────────────────────────────────────

class NewRoundIn(BaseModel):
    draw_date: str | None = None   # YYYY-MM-DD

@app.post("/api/admin/round/new")
async def admin_new_round(body: NewRoundIn = NewRoundIn(), _: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute("SELECT id FROM rounds WHERE status='open' LIMIT 1") as c:
            if await c.fetchone():
                raise HTTPException(400, "A round is already open")
        async with conn.execute(
            "INSERT INTO rounds (status, draw_date) VALUES ('open', ?)", (body.draw_date,)
        ) as c:
            rid = c.lastrowid
        await conn.commit()
        return {"round_id": rid}
    finally:
        await conn.close()

@app.post("/api/admin/round/close")
async def admin_close_round(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT id FROM rounds WHERE status='open' ORDER BY id DESC LIMIT 1"
        ) as c:
            row = await c.fetchone()
        if not row:
            raise HTTPException(400, "No open round to close")
        await conn.execute(
            "UPDATE rounds SET status='closed', closed_at=datetime('now') WHERE id=?", (row["id"],))
        await conn.commit()
        return {"round_id": row["id"], "status": "closed"}
    finally:
        await conn.close()

@app.post("/api/admin/round/draw")
async def admin_draw(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute(
            "SELECT * FROM rounds WHERE status='closed' ORDER BY id DESC LIMIT 1"
        ) as c:
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
        winner_id = random.choices(
            [p["user_id"] for p in parts], weights=[p["amount"] for p in parts], k=1)[0]
        winner = next(p for p in parts if p["user_id"] == winner_id)
        pct = round(winner["amount"] / pool * 100, 1) if pool else 0
        await conn.execute(
            "UPDATE users SET credit=credit+? WHERE telegram_id=?", (pool, winner_id))
        await conn.execute(
            "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
            (winner_id, "win", pool, f"Round #{rid} prize"))
        await conn.execute(
            "UPDATE rounds SET status='drawn', winner_id=?, drawn_at=datetime('now') WHERE id=?",
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
            """SELECT p.user_id, p.amount, u.full_name
               FROM participations p JOIN users u ON u.telegram_id=p.user_id
               WHERE p.round_id=? ORDER BY p.amount DESC""", (rid,)
        ) as c:
            parts = await c.fetchall()
        return {"round": {
            "id": rid, "status": row["status"],
            "display_status": display_status(row["status"], row["draw_date"]),
            "pool": pool, "draw_date": row["draw_date"],
            "opened_at": row["opened_at"], "closed_at": row["closed_at"],
            "drawn_at": row["drawn_at"], "winner_id": row["winner_id"],
            "participants": [{"user_id": p["user_id"], "full_name": p["full_name"],
                              "amount": p["amount"],
                              "pct": round(p["amount"] / pool * 100, 1) if pool else 0,
                              "won": p["user_id"] == row["winner_id"]}
                             for p in parts]}}
    finally:
        await conn.close()

@app.get("/api/admin/deposits")
async def admin_deposits(_: dict = Depends(trustee_only)):
    conn = await open_db()
    try:
        async with conn.execute(
            """SELECT dr.*, u.full_name, u.username FROM deposit_requests dr
               JOIN users u ON u.telegram_id=dr.user_id
               WHERE dr.status='pending' ORDER BY dr.created_at"""
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
            await conn.execute(
                "UPDATE users SET credit=credit+? WHERE telegram_id=?", (req["amount"], req["user_id"]))
            await conn.execute(
                "INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
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


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
