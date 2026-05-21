import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
TRUSTEE_ID: int = int(os.environ["TRUSTEE_TELEGRAM_ID"])
CURRENCY: str = os.getenv("CURRENCY", "USD")
DB_PATH: str = os.getenv("DB_PATH", "lotto.db")
