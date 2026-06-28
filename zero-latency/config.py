"""Environment configuration for the Zero Latency VR Richmond booking app."""

import os

from dotenv import load_dotenv

load_dotenv()

# Where bookings are stored. Defaults to a local SQLite file so the app runs with
# zero setup; point this at a Postgres URL (postgres://… or postgresql://…) in
# production and it will use asyncpg automatically.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./bookings.db")

# Stripe. Leave the secret key blank to run in demo mode (no real charges).
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

CURRENCY: str = os.getenv("CURRENCY", "CAD").upper()

# Public origin used to build Stripe success/cancel URLs. If blank it is derived
# from the incoming request (honouring x-forwarded-* proxy headers).
PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

PORT: int = int(os.getenv("PORT", "8000"))
