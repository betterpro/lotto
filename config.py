import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
TRUSTEE_ID: int = int(os.environ["TRUSTEE_TELEGRAM_ID"])
CURRENCY: str = os.getenv("CURRENCY", "CAD")
DB_PATH: str = os.getenv("DB_PATH", "lotto.db")
MINI_APP_URL: str = os.getenv("MINI_APP_URL", "")
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ADMIN_ETRANSFER_EMAIL: str = os.getenv("ADMIN_ETRANSFER_EMAIL", "")
IMAP_HOST: str = os.getenv("IMAP_HOST", "")
IMAP_USER: str = os.getenv("IMAP_USER", "")
IMAP_PASS: str = os.getenv("IMAP_PASS", "")
IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
