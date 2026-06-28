"""Zero Latency VR Richmond — booking website + Stripe Checkout.

A standalone FastAPI app: serves the booking front-end at ``/`` and a small REST
API under ``/api/*``. Bookings persist via db.py (SQLite by default, Postgres if
DATABASE_URL points at one).

Run locally:
    pip install -r requirements.txt
    uvicorn main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import booking as bk
import config
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("zl")

STATIC_DIR = Path(__file__).parent / "static"
HOLD_MINUTES = 20  # pending bookings keep their seats this long before freeing up


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    log.info("Database ready (%s)", "postgres" if config.DATABASE_URL.startswith("postgres") else "sqlite")
    if config.STRIPE_SECRET_KEY:
        stripe.api_key = config.STRIPE_SECRET_KEY
        log.info("Stripe enabled")
    else:
        log.warning("STRIPE_SECRET_KEY not set — running in DEMO mode (no real charges)")
    yield
    await db.close()


app = FastAPI(title="Zero Latency VR Richmond — Booking", lifespan=lifespan)


def base_url(request: Request) -> str:
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL
    env_url = os.environ.get("RENDER_EXTERNAL_URL")
    if env_url:
        return env_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


async def booked_players(experience_id: str, day: str) -> dict[str, int]:
    """{slot_time: players taken} counting confirmed + recent pending bookings."""
    cutoff = (datetime.utcnow() - timedelta(minutes=HOLD_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = await db.fetchall(
        """SELECT slot_time, COALESCE(SUM(players),0) AS taken
             FROM bookings
            WHERE experience_id=? AND slot_date=?
              AND (status='confirmed' OR (status='pending' AND created_at >= ?))
            GROUP BY slot_time""",
        (experience_id, day, cutoff),
    )
    return {r["slot_time"]: int(r["taken"]) for r in rows}


# ── API ──────────────────────────────────────────────────────────────────────
@app.get("/api/config")
async def api_config():
    return {
        "venue": {
            "id": bk.VENUE["id"], "name": bk.VENUE["name"], "brand": bk.VENUE["brand"],
            "tagline": bk.VENUE["tagline"], "address": bk.VENUE["address"],
            "timezone": bk.VENUE["timezone"], "horizon_days": bk.VENUE["booking_horizon_days"],
        },
        "currency": bk.CURRENCY,
        "stripe_enabled": bool(config.STRIPE_SECRET_KEY),
        "experiences": [bk.experience_public(e) for e in bk.EXPERIENCES],
        "today": bk.now_venue().date().isoformat(),
    }


@app.get("/api/availability")
async def api_availability(experience_id: str, date: str):
    exp = bk.EXPERIENCE_BY_ID.get(experience_id)
    if not exp:
        raise HTTPException(404, "Unknown experience")
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date (expected YYYY-MM-DD)")

    now = bk.now_venue()
    today = now.date()
    horizon = today + timedelta(days=bk.VENUE["booking_horizon_days"])
    if day < today or day > horizon:
        return {"date": date, "experience_id": experience_id, "slots": []}

    cap = bk.capacity(exp)
    taken = await booked_players(experience_id, date)
    slots = []
    for t in bk.slots_for(exp, date):
        if day == today and datetime.combine(day, t, tzinfo=bk.VENUE_TZ) <= now:
            continue  # hide already-started slots today
        remaining = max(0, cap - taken.get(t.strftime("%H:%M"), 0))
        slots.append({
            "time": t.strftime("%H:%M"),
            "label": t.strftime("%-I:%M %p"),
            "remaining": remaining,
            "soldout": remaining <= 0,
        })
    return {"date": date, "experience_id": experience_id, "capacity": cap, "slots": slots}


@app.post("/api/checkout")
async def api_checkout(request: Request):
    body = await request.json()
    experience_id = str(body.get("experience_id", ""))
    slot_date = str(body.get("date", ""))
    slot_time = str(body.get("time", ""))
    try:
        players = int(body.get("players", 0))
    except (TypeError, ValueError):
        players = 0
    name = (body.get("name") or "").strip()
    email = (body.get("email") or "").strip()
    phone = (body.get("phone") or "").strip()

    exp = bk.EXPERIENCE_BY_ID.get(experience_id)
    if not exp:
        raise HTTPException(400, "Please choose an experience.")
    if players < exp["min_players"] or players > exp["max_players"]:
        raise HTTPException(400, f"This experience takes {exp['min_players']}–{exp['max_players']} players.")
    if not name or "@" not in email:
        raise HTTPException(400, "Please enter your name and a valid email.")

    try:
        day = datetime.strptime(slot_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date.")
    if slot_time not in {t.strftime("%H:%M") for t in bk.slots_for(exp, slot_date)}:
        raise HTTPException(400, "That time isn't available — please pick another slot.")
    if datetime.combine(day, bk.parse_hhmm(slot_time), tzinfo=bk.VENUE_TZ) <= bk.now_venue():
        raise HTTPException(400, "That time has already started — please pick a later slot.")

    cap = bk.capacity(exp)
    taken = await booked_players(experience_id, slot_date)
    if taken.get(slot_time, 0) + players > cap:
        remaining = max(0, cap - taken.get(slot_time, 0))
        raise HTTPException(409, f"Only {remaining} spot(s) left in that session.")

    amount = exp["price"] * players
    ref = bk.gen_ref()
    await db.execute(
        """INSERT INTO bookings
             (ref, venue_id, experience_id, experience_name, slot_date, slot_time,
              players, unit_price, amount, currency, customer_name, customer_email,
              customer_phone, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?)""",
        (ref, bk.VENUE["id"], experience_id, exp["name"], slot_date, slot_time,
         players, exp["price"], amount, bk.CURRENCY, name, email, phone, db.utcnow_iso()),
    )

    base = base_url(request)
    success_url = f"{base}/confirmation.html?ref={ref}"
    cancel_url = f"{base}/?cancelled={ref}"

    if config.STRIPE_SECRET_KEY:
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
                customer_email=email,
                client_reference_id=ref,
                line_items=[{
                    "quantity": players,
                    "price_data": {
                        "currency": bk.CURRENCY.lower(),
                        "unit_amount": exp["price"],
                        "product_data": {
                            "name": f"{exp['name']} — {bk.VENUE['brand']} {bk.VENUE['name']}",
                            "description": f"{slot_date} at {slot_time} · {players} player(s)",
                        },
                    },
                }],
                metadata={
                    "ref": ref, "experience_id": experience_id,
                    "slot_date": slot_date, "slot_time": slot_time, "players": str(players),
                },
                expires_at=int((datetime.utcnow() + timedelta(minutes=35)).timestamp()),
            )
        except Exception as e:  # noqa: BLE001
            log.exception("stripe checkout error: %s", e)
            await db.execute("UPDATE bookings SET status='cancelled' WHERE ref=?", (ref,))
            raise HTTPException(400, getattr(e, "user_message", None) or "Could not start checkout.")
        await db.execute("UPDATE bookings SET stripe_session_id=? WHERE ref=?", (session.id, ref))
        return {"ref": ref, "checkout_url": session.url, "mode": "stripe"}

    # Demo mode — confirm immediately, clearly without taking payment.
    await db.execute(
        "UPDATE bookings SET status='confirmed', confirmed_at=? WHERE ref=?",
        (db.utcnow_iso(), ref),
    )
    log.warning("DEMO mode — booking %s confirmed WITHOUT payment.", ref)
    return {"ref": ref, "checkout_url": success_url, "mode": "demo"}


@app.post("/api/webhook")
async def api_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        if config.STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, config.STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
    except Exception as e:  # noqa: BLE001
        log.warning("webhook verify/parse failed: %s", e)
        raise HTTPException(400, "Invalid payload")

    etype = event["type"]
    obj = event["data"]["object"]
    ref = (obj.get("metadata") or {}).get("ref") or obj.get("client_reference_id")

    if etype == "checkout.session.completed" and ref:
        await db.execute(
            "UPDATE bookings SET status='confirmed', confirmed_at=?, stripe_payment_intent=? "
            "WHERE ref=? AND status<>'confirmed'",
            (db.utcnow_iso(), obj.get("payment_intent"), ref),
        )
        log.info("booking %s confirmed via Stripe", ref)
    elif etype == "checkout.session.expired" and ref:
        await db.execute("UPDATE bookings SET status='cancelled' WHERE ref=? AND status='pending'", (ref,))
    return JSONResponse({"received": True})


@app.get("/api/booking/{ref}")
async def api_booking(ref: str):
    row = await db.fetchone(
        """SELECT ref, experience_id, experience_name, slot_date, slot_time, players,
                  amount, currency, customer_name, customer_email, customer_phone, status
             FROM bookings WHERE ref=?""",
        (ref,),
    )
    if not row:
        raise HTTPException(404, "Booking not found")
    exp = bk.EXPERIENCE_BY_ID.get(row["experience_id"], {})
    row["emoji"] = exp.get("emoji", "🎮")
    row["accent"] = exp.get("accent", "#6d5cff")
    row["duration_min"] = exp.get("duration_min")
    row["amount_display"] = f"${row['amount'] / 100:.2f}"
    row["venue_name"] = bk.VENUE["name"]
    row["brand"] = bk.VENUE["brand"]
    return row


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ── Static front-end (must be mounted last) ──────────────────────────────────
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
