"""Web session auth via signed cookies + Telegram Login Widget validation."""

import hashlib
import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

import config

SESSION_COOKIE = "lottoo_session"
SESSION_MAX_AGE = 30 * 86400  # 30 days
LOGIN_MAX_AGE = 86400  # Telegram Login Widget auth_date window

# Web (non-Telegram) accounts get synthetic negative ids so they can never
# collide with real Telegram user ids, which are always positive. The id is
# allocated from the `web_user_id_seq` Postgres sequence (see database.py).
PASSWORD_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Return a self-describing pbkdf2_sha256 hash: algo$iters$salt$hash."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return "$".join([
        "pbkdf2_sha256",
        str(PASSWORD_ITERATIONS),
        salt.hex(),
        dk.hex(),
    ])


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    return hmac.compare_digest(dk, expected)


def _signing_key() -> bytes:
    return hashlib.sha256(config.BOT_TOKEN.encode()).digest()


def create_session_token(telegram_id: int) -> str:
    payload = {"uid": telegram_id, "exp": int(time.time()) + SESSION_MAX_AGE}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(_signing_key(), raw, hashlib.sha256).hexdigest()
    return urlsafe_b64encode(raw).decode().rstrip("=") + "." + sig


def verify_session_token(token: str) -> int | None:
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    pad = "=" * (-len(b64) % 4)
    try:
        raw = urlsafe_b64decode(b64 + pad)
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    expected = hmac.new(_signing_key(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    uid = payload.get("uid")
    exp = payload.get("exp")
    if not isinstance(uid, int) or not isinstance(exp, int) or exp < time.time():
        return None
    return uid


def validate_telegram_login(data: dict) -> dict | None:
    """Validate Telegram Login Widget payload. Returns user fields or None."""
    received_hash = data.get("hash")
    if not received_hash:
        return None
    auth_date = data.get("auth_date")
    if auth_date is None:
        return None
    try:
        auth_ts = int(auth_date)
    except (TypeError, ValueError):
        return None
    if time.time() - auth_ts > LOGIN_MAX_AGE:
        return None

    check_pairs = []
    for k, v in sorted(data.items()):
        if k == "hash":
            continue
        check_pairs.append(f"{k}={v}")
    data_check = "\n".join(check_pairs)
    secret = hashlib.sha256(config.BOT_TOKEN.encode()).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(received_hash)):
        return None

    try:
        uid = int(data["id"])
    except (KeyError, TypeError, ValueError):
        return None

    return {
        "id": uid,
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "username": data.get("username"),
        "photo_url": data.get("photo_url"),
    }
