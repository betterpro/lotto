import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
TRUSTEE_ID: int = int(os.environ["TRUSTEE_TELEGRAM_ID"])
CURRENCY: str = os.getenv("CURRENCY", "CAD")
DB_PATH: str = os.getenv("DB_PATH", "lotto.db")
MINI_APP_URL: str = os.getenv("MINI_APP_URL", "")
