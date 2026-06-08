"""Next draw dates and estimated jackpots for Canadian national lottery games."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from lottery_types import valid_lottery_type

PT = ZoneInfo("America/Vancouver")

# weekday(): Mon=0 … Sun=6 — draw cutoffs in Pacific time
DRAW_SCHEDULE: dict[str, dict] = {
    "lotto_max": {"weekdays": (1, 4), "hour": 19, "minute": 30},   # Tue, Fri 7:30 PM PT
    "649": {"weekdays": (2, 5), "hour": 19, "minute": 30},         # Wed, Sat 7:30 PM PT
    "daily_grand": {"weekdays": (0, 3), "hour": 19, "minute": 21}, # Mon, Thu 7:21 PM PT
}

WCLC_GAME_URL = {
    "lotto_max": "https://www.wclc.com/games/lotto-max.htm",
    "649": "https://www.wclc.com/games/lotto-649.htm",
}

WCLC_JACKPOT_SECTION = {
    "lotto_max": "Lmax",
    "649": "L649gold",
}

# Lump-sum equivalent for the top Daily Grand prize ($1,000/day for life).
DAILY_GRAND_JACKPOT = 7_000_000

_USER_AGENT = "Mozilla/5.0 (compatible; LottoPool/1.0; +https://github.com/lotto)"


def next_draw_date(lottery_type: str, *, from_dt: datetime | None = None) -> date | None:
    """Return the next draw calendar date for a lottery type (Pacific cutoff)."""
    if not valid_lottery_type(lottery_type):
        return None
    sched = DRAW_SCHEDULE[lottery_type]
    draw_days = set(sched["weekdays"])
    now = (from_dt or datetime.now(PT)).astimezone(PT)
    cutoff = now.replace(hour=sched["hour"], minute=sched["minute"], second=0, microsecond=0)
    start = now.date()
    if start.weekday() in draw_days and now < cutoff:
        return start
    for offset in range(1, 8):
        candidate = start + timedelta(days=offset)
        if candidate.weekday() in draw_days:
            return candidate
    return None


def upcoming_draw_dates(
    lottery_type: str,
    *,
    count: int = 12,
    from_dt: datetime | None = None,
) -> list[date]:
    """Return the next scheduled draw dates for a lottery type."""
    if not valid_lottery_type(lottery_type) or count < 1:
        return []
    dates: list[date] = []
    probe = from_dt or datetime.now(PT)
    for _ in range(count):
        nd = next_draw_date(lottery_type, from_dt=probe)
        if not nd:
            break
        dates.append(nd)
        probe = datetime.combine(nd + timedelta(days=1), datetime.min.time(), PT)
    return dates


def _parse_wclc_jackpot_millions(html: str, section: str) -> int | None:
    marker = f'nextJackpotDetails{section}'
    start = html.find(marker)
    if start < 0:
        return None
    end = html.find("<!-- end next jackpot details", start)
    chunk = html[start:end if end > start else start + 4000]
    m = re.search(r'nextJackpotPrizeAmount">(\d+)', chunk)
    if not m:
        return None
    return int(m.group(1)) * 1_000_000


async def fetch_estimated_jackpot(lottery_type: str) -> int | None:
    """Fetch the current estimated jackpot (CAD cents as integer dollars)."""
    if not valid_lottery_type(lottery_type):
        return None
    if lottery_type == "daily_grand":
        return DAILY_GRAND_JACKPOT

    section = WCLC_JACKPOT_SECTION.get(lottery_type)
    url = WCLC_GAME_URL.get(lottery_type)
    if not section or not url:
        return None

    try:
        async with httpx.AsyncClient(
            timeout=12.0,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return _parse_wclc_jackpot_millions(resp.text, section)
    except Exception:
        return None


def is_valid_draw_date(
    lottery_type: str, draw: date, *, from_dt: datetime | None = None
) -> bool:
    """True if draw is a scheduled draw day on or after today (Pacific cutoff)."""
    if not valid_lottery_type(lottery_type):
        return False
    sched = DRAW_SCHEDULE[lottery_type]
    now = (from_dt or datetime.now(PT)).astimezone(PT)
    if draw < now.date():
        return False
    if draw.weekday() not in sched["weekdays"]:
        return False
    if draw == now.date():
        cutoff = now.replace(
            hour=sched["hour"], minute=sched["minute"], second=0, microsecond=0
        )
        if now >= cutoff:
            return False
    return True


async def suggest_new_round(
    lottery_type: str,
    *,
    draw_date: str | date | None = None,
    from_dt: datetime | None = None,
) -> dict:
    """Suggested draw_date and jackpot for opening a new round."""
    next_draw = next_draw_date(lottery_type, from_dt=from_dt)
    available_dates = upcoming_draw_dates(lottery_type, from_dt=from_dt)
    available_iso = [d.isoformat() for d in available_dates]

    if draw_date:
        selected = date.fromisoformat(draw_date) if isinstance(draw_date, str) else draw_date
        if not is_valid_draw_date(lottery_type, selected, from_dt=from_dt):
            return {
                "lottery_type": lottery_type,
                "draw_date": None,
                "draw_dates": available_iso,
                "next_draw_date": next_draw.isoformat() if next_draw else None,
                "jackpot": 0,
                "jackpot_available": False,
                "error": "invalid_draw_date",
            }
    else:
        selected = next_draw

    jackpot_available = bool(next_draw and selected == next_draw)
    jackpot = 0
    if jackpot_available:
        fetched = await fetch_estimated_jackpot(lottery_type)
        jackpot = fetched or 0
        jackpot_available = jackpot > 0

    return {
        "lottery_type": lottery_type,
        "draw_date": selected.isoformat() if selected else None,
        "draw_dates": available_iso,
        "next_draw_date": next_draw.isoformat() if next_draw else None,
        "jackpot": jackpot,
        "jackpot_available": jackpot_available,
    }
