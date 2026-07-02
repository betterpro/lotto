"""Transactional email via Resend (https://resend.com).

All functions no-op gracefully when RESEND_API_KEY / RESEND_FROM are unset, so
the app runs fine without email configured. Sending never raises into a request.
"""

import base64
import logging

import httpx

import config

log = logging.getLogger("emailer")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def email_enabled() -> bool:
    return bool(config.RESEND_API_KEY and config.RESEND_FROM)


async def send_email(to, subject: str, html_body: str, *, attachments=None, reply_to=None) -> bool:
    """Send one email through Resend. Returns True on success.

    attachments: list of Resend attachment dicts, e.g.
      {"filename": "x.pdf", "content": "<base64>"}  or
      {"filename": "t.jpg", "path": "https://…"}
    """
    if not email_enabled() or not to:
        return False
    payload = {
        "from": config.RESEND_FROM,
        "to": [to] if isinstance(to, str) else list(to),
        "subject": subject,
        "html": html_body,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if attachments:
        payload["attachments"] = attachments
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                RESEND_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {config.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 300:
            log.warning("resend send failed %s: %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as e:
        log.warning("resend send error: %s", e)
        return False


def pdf_attachment(filename: str, data: bytes) -> dict:
    """Build a Resend attachment from raw PDF bytes."""
    return {"filename": filename, "content": base64.b64encode(data).decode("ascii")}


def image_attachment(filename: str, image: str) -> dict | None:
    """Build a Resend attachment from a stored ticket image.

    The image is either a full http(s) URL (Supabase storage) or raw base64
    (optionally with a `data:` prefix).
    """
    if not image:
        return None
    if image.startswith("http://") or image.startswith("https://"):
        return {"filename": filename, "path": image}
    b64 = image.split(",", 1)[-1] if image.startswith("data:") else image
    return {"filename": filename, "content": b64}
