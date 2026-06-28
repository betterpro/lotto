"""
VR experience booking — a self-contained "book a time slot + pay with Stripe"
feature, modelled on the Zero Latency VR booking flow
(booking.zerolatencyvr.com).

It is intentionally isolated from the lottery app: all of its routes live under
``/api/vr/*`` and the booking page is served at ``/book``. The only shared
infrastructure is the FastAPI app, the Postgres pool (via ``database.get_db``)
and the platform Stripe key (``config.STRIPE_SECRET_KEY``).

Wire-up (done in api.py)::

    import vr_booking
    vr_booking.register(app)

Bookings are stored in the ``vr_bookings`` table (created idempotently by
``database.ensure_schema`` / migration 015).
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

import config
from database import ensure_schema, get_db

log = logging.getLogger("vr_booking")

# ── Venue ────────────────────────────────────────────────────────────────────
# A single location for now; the model is data-driven so more can be added.
VENUE = {
    "id": "richmond-city",
    "name": "Richmond City",
    "brand": "ZERO LATENCY VR",
    "tagline": "Free-roam virtual reality. Up to 8 players. One unforgettable mission.",
    "timezone": "America/Vancouver",
    "address": "Lansdowne Centre, Richmond, BC",
    # Operating hours per ISO weekday (1=Mon … 7=Sun): (open "HH:MM", close "HH:MM").
    # Sessions can start from `open` up to (close − experience duration).
    "hours": {
        1: ("12:00", "21:00"),
        2: ("12:00", "21:00"),
        3: ("12:00", "21:00"),
        4: ("12:00", "22:00"),
        5: ("10:00", "23:00"),
        6: ("10:00", "23:00"),
        7: ("10:00", "21:00"),
    },
    # Minutes between session start times.
    "slot_interval": 30,
    # How many separate arenas the venue can run concurrently. With 1 arena a
    # time slot's capacity is the experience's max party size.
    "arenas": 1,
    # How far ahead guests may book.
    "booking_horizon_days": 30,
}

VENUE_TZ = ZoneInfo(VENUE["timezone"])

# ── Experiences (games) ──────────────────────────────────────────────────────
# Posters are rendered client-side from `accent`/`emoji`/`tag` so the page never
# shows a broken image and needs no external assets.
EXPERIENCES = [
    {
        "id": "outbreak",
        "name": "Outbreak",
        "tag": "Zombie Survival",
        "emoji": "🧟",
        "accent": "#16a34a",
        "duration_min": 50,
        "min_players": 1,
        "max_players": 8,
        "price": 5900,  # cents
        "intensity": "Intense",
        "min_age": 13,
        "summary": "Fight your way out of a zombie-infested megacity in our most popular free-roam mission.",
    },
    {
        "id": "sol-raiders",
        "name": "Sol Raiders",
        "tag": "Competitive PvP",
        "emoji": "⚔️",
        "accent": "#f59e0b",
        "duration_min": 30,
        "min_players": 2,
        "max_players": 8,
        "price": 4900,
        "intensity": "Moderate",
        "min_age": 13,
        "summary": "Two teams, three arenas, one trophy. Capture the relays and outgun your rivals.",
    },
    {
        "id": "engineerium",
        "name": "Engineerium",
        "tag": "Exploration",
        "emoji": "🪐",
        "accent": "#8b5cf6",
        "duration_min": 30,
        "min_players": 1,
        "max_players": 8,
        "price": 4900,
        "intensity": "Relaxed",
        "min_age": 8,
        "summary": "A gravity-bending walk through an impossible alien world. Perfect for first-timers.",
    },
    {
        "id": "far-cry-vr",
        "name": "Far Cry VR: Dive Into Insanity",
        "tag": "Action Shooter",
        "emoji": "🌴",
        "accent": "#ef4444",
        "duration_min": 45,
        "min_players": 1,
        "max_players": 8,
        "price": 5900,
        "intensity": "Intense",
        "min_age": 16,
        "summary": "Escape Hope County's deadly cult across a sprawling tropical battleground.",
    },
    {
        "id": "undead-arena",
        "name": "Undead Arena",
        "tag": "Game Show Horror",
        "emoji": "🎯",
        "accent": "#06b6d4",
        "duration_min": 40,
        "min_players": 1,
        "max_players": 8,
        "price": 5500,
        "intensity": "Moderate",
        "min_age": 13,
        "summary": "Become a contestant in a televised zombie blood-sport. Score points, stay alive.",
    },
    {
        "id": "singularity",
        "name": "Singularity",
        "tag": "Sci-Fi Shooter",
        "emoji": "🤖",
        "accent": "#3b82f6",
        "duration_min": 30,
        "min_players": 1,
        "max_players": 8,
        "price": 4900,
        "intensity": "Intense",
        "min_age": 13,
        "summary": "A rogue AI has overrun the station. Fight room to room to shut it down.",
    },
]

EXPERIENCE_BY_ID = {e["id"]: e for e in EXPERIENCES}

CURRENCY = (config.CURRENCY or "CAD").upper()


# ── Helpers ──────────────────────────────────────────────────────────────────
def _now_venue() -> datetime:
    return datetime.now(VENUE_TZ)


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _gen_ref() -> str:
    alphabet = string.ascii_uppercase + string.digits
    # Avoid easily-confused chars.
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "VR-" + "".join(secrets.choice(alphabet) for _ in range(6))


def _experience_public(e: dict) -> dict:
    return {
        "id": e["id"],
        "name": e["name"],
        "tag": e["tag"],
        "emoji": e["emoji"],
        "accent": e["accent"],
        "duration_min": e["duration_min"],
        "min_players": e["min_players"],
        "max_players": e["max_players"],
        "price": e["price"],
        "price_display": f"${e['price'] / 100:.0f}",
        "intensity": e["intensity"],
        "min_age": e["min_age"],
        "summary": e["summary"],
        "currency": CURRENCY,
    }


async def _booked_players_for_date(db, experience_id: str, day: str) -> dict[str, int]:
    """Return {slot_time: total_players} for live (pending/confirmed) bookings.

    Pending bookings are counted too so a guest part-way through checkout can't be
    double-booked; abandoned pendings free up via the 20-minute hold window.
    """
    cutoff = (datetime.utcnow() - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    cur = await db.execute(
        """SELECT slot_time, COALESCE(SUM(players),0) AS taken
             FROM vr_bookings
            WHERE experience_id=? AND slot_date=?
              AND (status='confirmed' OR (status='pending' AND created_at >= ?))
            GROUP BY slot_time""",
        (experience_id, day, cutoff),
    )
    rows = await cur.fetchall()
    out: dict[str, int] = {}
    for r in rows:
        out[r["slot_time"]] = int(r["taken"])
    return out


def _slots_for(experience: dict, day: str) -> list[time]:
    d = date.fromisoformat(day)
    hours = VENUE["hours"].get(d.isoweekday())
    if not hours:
        return []
    open_t = _parse_hhmm(hours[0])
    close_t = _parse_hhmm(hours[1])
    interval = VENUE["slot_interval"]
    dur = experience["duration_min"]
    cursor = datetime.combine(d, open_t)
    # Last start so the session finishes by closing time.
    last_start = datetime.combine(d, close_t) - timedelta(minutes=dur)
    slots: list[time] = []
    while cursor <= last_start:
        slots.append(cursor.time())
        cursor += timedelta(minutes=interval)
    return slots


# ── App registration ─────────────────────────────────────────────────────────
def register(app: FastAPI) -> None:
    """Attach booking routes + static page. Call before the SPA catch-all mount."""

    @app.get("/api/vr/config")
    async def vr_config():
        return {
            "venue": {
                "id": VENUE["id"],
                "name": VENUE["name"],
                "brand": VENUE["brand"],
                "tagline": VENUE["tagline"],
                "address": VENUE["address"],
                "timezone": VENUE["timezone"],
                "horizon_days": VENUE["booking_horizon_days"],
            },
            "currency": CURRENCY,
            "stripe_enabled": bool(config.STRIPE_SECRET_KEY),
            "experiences": [_experience_public(e) for e in EXPERIENCES],
            "today": _now_venue().date().isoformat(),
        }

    @app.get("/api/vr/availability")
    async def vr_availability(experience_id: str, date: str):
        exp = EXPERIENCE_BY_ID.get(experience_id)
        if not exp:
            raise HTTPException(404, "Unknown experience")
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date (expected YYYY-MM-DD)")

        now = _now_venue()
        today = now.date()
        horizon = today + timedelta(days=VENUE["booking_horizon_days"])
        if day < today or day > horizon:
            return {"date": date, "experience_id": experience_id, "slots": []}

        capacity = exp["max_players"] * VENUE["arenas"]
        db = await get_db()
        try:
            taken = await _booked_players_for_date(db, experience_id, date)
        finally:
            await db.close()

        slots = []
        for t in _slots_for(exp, date):
            hhmm = t.strftime("%H:%M")
            # Hide already-started slots for today.
            if day == today and datetime.combine(day, t, tzinfo=VENUE_TZ) <= now:
                continue
            used = taken.get(hhmm, 0)
            remaining = max(0, capacity - used)
            slots.append({
                "time": hhmm,
                "label": t.strftime("%-I:%M %p"),
                "remaining": remaining,
                "soldout": remaining <= 0,
            })
        return {
            "date": date,
            "experience_id": experience_id,
            "capacity": capacity,
            "slots": slots,
        }

    @app.post("/api/vr/checkout")
    async def vr_checkout(request: Request):
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

        exp = EXPERIENCE_BY_ID.get(experience_id)
        if not exp:
            raise HTTPException(400, "Please choose an experience.")
        if players < exp["min_players"] or players > exp["max_players"]:
            raise HTTPException(400, f"This experience takes {exp['min_players']}–{exp['max_players']} players.")
        if not name or "@" not in email:
            raise HTTPException(400, "Please enter your name and a valid email.")

        # Validate the slot exists for that date/experience.
        try:
            day = datetime.strptime(slot_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(400, "Invalid date.")
        valid_times = {t.strftime("%H:%M") for t in _slots_for(exp, slot_date)}
        if slot_time not in valid_times:
            raise HTTPException(400, "That time isn't available — please pick another slot.")
        now = _now_venue()
        if datetime.combine(day, _parse_hhmm(slot_time), tzinfo=VENUE_TZ) <= now:
            raise HTTPException(400, "That time has already started — please pick a later slot.")

        capacity = exp["max_players"] * VENUE["arenas"]
        amount = exp["price"] * players

        db = await get_db()
        try:
            taken = await _booked_players_for_date(db, experience_id, slot_date)
            if taken.get(slot_time, 0) + players > capacity:
                remaining = max(0, capacity - taken.get(slot_time, 0))
                raise HTTPException(409, f"Only {remaining} spot(s) left in that session.")

            ref = _gen_ref()
            cur = await db.execute(
                """INSERT INTO vr_bookings
                     (ref, venue_id, experience_id, experience_name, slot_date, slot_time,
                      players, unit_price, amount, currency, customer_name, customer_email,
                      customer_phone, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending', datetime('now'))
                   RETURNING id""",
                (ref, VENUE["id"], experience_id, exp["name"], slot_date, slot_time,
                 players, exp["price"], amount, CURRENCY, name, email, phone),
            )
            row = await cur.fetchone()
            booking_id = row["id"] if row else None

            base = _base_url(request)
            success_url = f"{base}/book/confirmation.html?ref={ref}"
            cancel_url = f"{base}/book/?cancelled={ref}"

            if config.STRIPE_SECRET_KEY:
                stripe.api_key = config.STRIPE_SECRET_KEY
                session = stripe.checkout.Session.create(
                    mode="payment",
                    success_url=success_url + "&session_id={CHECKOUT_SESSION_ID}",
                    cancel_url=cancel_url,
                    customer_email=email,
                    client_reference_id=ref,
                    line_items=[{
                        "quantity": players,
                        "price_data": {
                            "currency": CURRENCY.lower(),
                            "unit_amount": exp["price"],
                            "product_data": {
                                "name": f"{exp['name']} — {VENUE['brand']} {VENUE['name']}",
                                "description": f"{slot_date} at {slot_time} · {players} player(s)",
                            },
                        },
                    }],
                    metadata={
                        "ref": ref,
                        "booking_id": str(booking_id),
                        "experience_id": experience_id,
                        "slot_date": slot_date,
                        "slot_time": slot_time,
                        "players": str(players),
                    },
                    expires_at=int((datetime.utcnow() + timedelta(minutes=35)).timestamp()),
                )
                await db.execute(
                    "UPDATE vr_bookings SET stripe_session_id=? WHERE ref=?",
                    (session.id, ref),
                )
                return {"ref": ref, "checkout_url": session.url, "mode": "stripe"}

            # No Stripe configured → confirm immediately so the flow is usable in
            # demo/dev. Clearly flagged so it can't be mistaken for a real charge.
            await db.execute(
                "UPDATE vr_bookings SET status='confirmed', confirmed_at=datetime('now') WHERE ref=?",
                (ref,),
            )
            log.warning("Stripe not configured — booking %s confirmed WITHOUT payment.", ref)
            return {"ref": ref, "checkout_url": success_url, "mode": "demo"}
        except HTTPException:
            raise
        except Exception as e:
            log.exception("vr checkout error: %s", e)
            msg = getattr(e, "user_message", None) or "Could not start checkout."
            raise HTTPException(400, msg)
        finally:
            await db.close()

    @app.post("/api/vr/webhook")
    async def vr_webhook(request: Request):
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        secret = config.STRIPE_WEBHOOK_SECRET
        try:
            if secret:
                event = stripe.Webhook.construct_event(payload, sig, secret)
            else:
                import json
                event = json.loads(payload)
        except Exception as e:
            log.warning("vr webhook signature/parse error: %s", e)
            raise HTTPException(400, "Invalid payload")

        etype = event.get("type") if isinstance(event, dict) else event["type"]
        obj = (event.get("data", {}) or {}).get("object", {}) if isinstance(event, dict) else event["data"]["object"]

        if etype == "checkout.session.completed":
            ref = (obj.get("metadata") or {}).get("ref") or obj.get("client_reference_id")
            if ref:
                db = await get_db()
                try:
                    await db.execute(
                        """UPDATE vr_bookings
                              SET status='confirmed', confirmed_at=datetime('now'),
                                  stripe_payment_intent=?
                            WHERE ref=? AND status<>'confirmed'""",
                        (obj.get("payment_intent"), ref),
                    )
                finally:
                    await db.close()
                log.info("vr booking %s confirmed via Stripe", ref)
        elif etype in ("checkout.session.expired",):
            ref = (obj.get("metadata") or {}).get("ref") or obj.get("client_reference_id")
            if ref:
                db = await get_db()
                try:
                    await db.execute(
                        "UPDATE vr_bookings SET status='cancelled' WHERE ref=? AND status='pending'",
                        (ref,),
                    )
                finally:
                    await db.close()
        return JSONResponse({"received": True})

    @app.get("/api/vr/booking/{ref}")
    async def vr_booking_status(ref: str):
        db = await get_db()
        try:
            cur = await db.execute(
                """SELECT ref, experience_id, experience_name, slot_date, slot_time,
                          players, amount, currency, customer_name, customer_email,
                          customer_phone, status
                     FROM vr_bookings WHERE ref=?""",
                (ref,),
            )
            row = await cur.fetchone()
        finally:
            await db.close()
        if not row:
            raise HTTPException(404, "Booking not found")
        b = dict(row)
        exp = EXPERIENCE_BY_ID.get(b["experience_id"], {})
        b["emoji"] = exp.get("emoji", "🎮")
        b["accent"] = exp.get("accent", "#3b82f6")
        b["duration_min"] = exp.get("duration_min")
        b["amount_display"] = f"${b['amount'] / 100:.2f}"
        b["venue_name"] = VENUE["name"]
        b["brand"] = VENUE["brand"]
        return b

    # Static booking page (no build step) — served at /book.
    static_dir = Path(__file__).parent / "vr_booking"
    if static_dir.is_dir():
        app.mount("/book", StaticFiles(directory=str(static_dir), html=True), name="vrbook")

    log.info("VR booking module registered (/book, /api/vr/*)")


def _base_url(request: Request) -> str:
    # Honour proxy headers on Render so redirect URLs use https + the public host.
    import os
    env_url = os.environ.get("RENDER_EXTERNAL_URL") or config.MINI_APP_URL
    if env_url:
        return env_url.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"
