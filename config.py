import os

from dotenv import load_dotenv



load_dotenv()





def _require_env(name: str) -> str:

    val = os.getenv(name, "").strip()

    if not val:

        raise RuntimeError(

            f"Missing required environment variable {name}. "

            "Set it in Render → your service → Environment "

            "(PLATFORM_ADMIN_TELEGRAM_IDS = comma-separated Telegram user ids)."

        )

    return val





BOT_TOKEN: str = _require_env("BOT_TOKEN")

DATABASE_URL: str = _require_env("DATABASE_URL")





def _parse_admin_ids() -> set[int]:

    raw = _require_env("PLATFORM_ADMIN_TELEGRAM_IDS")

    ids = {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}

    if not ids:

        raise RuntimeError(

            "PLATFORM_ADMIN_TELEGRAM_IDS must contain at least one numeric Telegram user id."

        )

    return ids





PLATFORM_ADMIN_IDS: set[int] = _parse_admin_ids()



CURRENCY: str = os.getenv("CURRENCY", "CAD")

MINI_APP_URL: str = os.getenv("MINI_APP_URL", "")

STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")

STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")

SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")

ADMIN_ETRANSFER_EMAIL: str = os.getenv("ADMIN_ETRANSFER_EMAIL", "")

# Auto-fetch official winning numbers and notify match results (best-effort WCLC
# scrape). Set AUTO_RESULTS_ENABLED=0 to disable if the scrape misbehaves.
AUTO_RESULTS_ENABLED: bool = os.getenv("AUTO_RESULTS_ENABLED", "1") == "1"

IMAP_HOST: str = os.getenv("IMAP_HOST", "")

IMAP_USER: str = os.getenv("IMAP_USER", "")

IMAP_PASS: str = os.getenv("IMAP_PASS", "")

IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))

ETRANSFER_CHECK_INTERVAL_SECONDS: int = int(os.getenv("ETRANSFER_CHECK_INTERVAL_SECONDS", "120"))


