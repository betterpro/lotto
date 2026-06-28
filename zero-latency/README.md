# Zero Latency VR Richmond — Booking

A standalone booking website for the Richmond City branch: guests pick an
experience, date, session time and party size, then pay with **Stripe**. Built as
a single self-contained FastAPI app — no build step, no framework lock-in.

It is completely independent (its own server, database layer, config and
front-end) and shares nothing with any other project.

## Quick start

```bash
cd zero-latency
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional — runs in demo mode if left blank
uvicorn main:app --reload
```

Open <http://localhost:8000>. With no Stripe key set, the app runs in **demo
mode**: bookings are confirmed instantly without a real charge (clearly
labelled), so you can click through the whole flow immediately. Data is stored in
a local `bookings.db` SQLite file.

## Connecting Stripe

1. Set `STRIPE_SECRET_KEY` (and `STRIPE_PUBLISHABLE_KEY`) in `.env`.
2. Set `STRIPE_WEBHOOK_SECRET` and add a webhook in the Stripe dashboard pointing
   at `https://<your-host>/api/webhook`, subscribed to:
   - `checkout.session.completed`
   - `checkout.session.expired`
3. Set `PUBLIC_BASE_URL` to your public origin so Stripe redirect links are
   correct (e.g. `https://book.example.com`).

The checkout flow uses Stripe **Checkout Sessions** (hosted payment page). When a
session completes, the webhook marks the booking `confirmed`; the confirmation
page polls until it flips.

## Deploy to Render

The included `render.yaml` is a Blueprint that provisions both the web service
and a Postgres database, and wires `DATABASE_URL` between them automatically.

1. Push this project to a Git repo (its folder must be the **repo root**, so
   `render.yaml` sits at the top level).
2. Render Dashboard → **New → Blueprint** → pick the repo → **Apply**. Render
   creates the Postgres DB and the web service.
3. In the service's **Environment**, add your Stripe keys:
   `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, and
   set `PUBLIC_BASE_URL` to the service's URL
   (e.g. `https://zero-latency-booking.onrender.com`).
4. In **Stripe → Developers → Webhooks**, add an endpoint at
   `https://<your-url>/api/webhook` for `checkout.session.completed` and
   `checkout.session.expired`, then copy its signing secret into
   `STRIPE_WEBHOOK_SECRET` and redeploy.

Health check: `GET /healthz`. The `bookings` table is created automatically on
first boot. Until you set `STRIPE_SECRET_KEY` the live site runs in demo mode.

## How it works

| Step | What happens |
| ---- | ------------ |
| 1. Experience | Cards generated from `EXPERIENCES` in `booking.py` |
| 2. Date | Next `booking_horizon_days` days |
| 3. Time | Slots generated from the venue's opening hours minus the experience length; shows live "spots left" |
| 4. Players | Clamped to the experience's min/max and the slot's remaining capacity |
| 5. Details | Name, email, phone |
| 6. Pay | Stripe Checkout → confirmation page |

## Configuration

Everything a non-developer is likely to change lives in **`booking.py`**:

- `VENUE` — name, address, timezone, opening hours per weekday, slot interval,
  number of arenas, booking horizon.
- `EXPERIENCES` — each game's name, blurb, duration, party size, price (in
  cents), intensity and minimum age.

Environment variables are documented in `.env.example`.

## Database

`db.py` uses **SQLite** by default (zero setup). Set `DATABASE_URL` to a
`postgres://…` / `postgresql://…` connection string to use Postgres (via
asyncpg) — recommended for production. The schema is created automatically on
startup; `migrations/001_init.sql` has it for reference.

## Project layout

```
zero-latency/
├── main.py              # FastAPI app + REST API + static hosting
├── booking.py           # venue, experiences, scheduling logic
├── db.py                # SQLite/Postgres data layer
├── config.py            # env configuration
├── requirements.txt
├── render.yaml          # one-click Render deploy
├── migrations/001_init.sql
└── static/              # index.html, confirmation.html, styles.css, app.js
```

## API

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET | `/api/config` | Venue + experiences + currency + today |
| GET | `/api/availability?experience_id=&date=` | Session times with remaining capacity |
| POST | `/api/checkout` | Create a booking + Stripe Checkout session |
| POST | `/api/webhook` | Stripe webhook (confirm / expire) |
| GET | `/api/booking/{ref}` | Booking status for the confirmation page |
| GET | `/healthz` | Health check |
