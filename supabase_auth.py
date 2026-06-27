"""Supabase Auth integration — verify JWTs and sync auth.users → public.users."""

from __future__ import annotations

import logging

import httpx

import config
from database import create_web_user, get_user, get_user_by_auth_email, get_user_by_auth_user_id

log = logging.getLogger(__name__)


async def verify_supabase_access_token(token: str) -> dict | None:
    """Validate a Supabase access token and return the auth user payload."""
    if not token or not config.SUPABASE_URL or not config.SUPABASE_SERVICE_KEY:
        return None
    url = f"{config.SUPABASE_URL.rstrip('/')}/auth/v1/user"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": config.SUPABASE_SERVICE_KEY,
                },
            )
    except httpx.HTTPError as exc:
        log.debug("Supabase auth verify failed: %s", exc)
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    user = data.get("user") if isinstance(data, dict) else None
    return user if isinstance(user, dict) and user.get("id") else None


def _provider_from_supabase_user(su: dict) -> str:
    app_meta = su.get("app_metadata") or {}
    provider = app_meta.get("provider")
    if provider:
        return str(provider)
    identities = su.get("identities") or []
    if identities and identities[0].get("provider"):
        return str(identities[0]["provider"])
    return "email"


def _full_name_from_supabase_user(su: dict) -> str | None:
    meta = su.get("user_metadata") or {}
    for key in ("full_name", "name"):
        val = (meta.get(key) or "").strip()
        if val:
            return val
    first = (meta.get("first_name") or meta.get("given_name") or "").strip()
    last = (meta.get("last_name") or meta.get("family_name") or "").strip()
    combined = " ".join(x for x in (first, last) if x)
    return combined or None


def _photo_from_supabase_user(su: dict) -> str | None:
    meta = su.get("user_metadata") or {}
    for key in ("avatar_url", "picture"):
        val = meta.get(key)
        if val:
            return str(val)
    return None


async def ensure_app_user_from_supabase(db, *, su: dict):
    """Ensure a public.users row exists for this Supabase Auth user."""
    auth_user_id = str(su["id"])
    email = (su.get("email") or "").strip().lower() or None
    full_name = _full_name_from_supabase_user(su)
    photo_url = _photo_from_supabase_user(su)
    provider = _provider_from_supabase_user(su)

    user = await get_user_by_auth_user_id(db, auth_user_id)
    if user:
        sets, params = [], []
        if email and not user.get("auth_email"):
            sets.append("auth_email = ?")
            params.append(email)
        if photo_url and not user.get("photo_url"):
            sets.append("photo_url = ?")
            params.append(photo_url)
        if sets:
            params.append(user["telegram_id"])
            await db.execute(
                f"UPDATE users SET {', '.join(sets)} WHERE telegram_id = ?",
                tuple(params),
            )
            await db.commit()
            user = await get_user(db, user["telegram_id"])
        return user

    if email:
        existing = await get_user_by_auth_email(db, email)
        if existing:
            await db.execute(
                """UPDATE users SET auth_user_id=?, auth_provider=?,
                   photo_url=COALESCE(photo_url, ?) WHERE telegram_id=?""",
                (auth_user_id, provider, photo_url, existing["telegram_id"]),
            )
            await db.commit()
            return await get_user(db, existing["telegram_id"])

    display = full_name or (email.split("@")[0] if email else "Member")
    return await create_web_user(
        db,
        display,
        auth_email=email,
        auth_user_id=auth_user_id,
        auth_provider=provider,
        photo_url=photo_url,
    )
