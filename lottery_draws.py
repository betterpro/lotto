"""Next draw dates and estimated jackpots for Canadian national lottery games."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
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


# --- Official winning numbers (auto-results) ---------------------------------
# WCLC publishes the latest winning numbers on the game page. Parsing is
# best-effort and conservative: it only returns a result when the page clearly
# shows the requested draw date alongside exactly the expected count of numbers
# in range. If anything is off it returns None (the trustee enters results
# manually). The HTML structure should be verified against the live page.
WCLC_WINNING_URL = {
    "lotto_max": "https://www.wclc.com/games/lotto-max.htm",
    "649": "https://www.wclc.com/games/lotto-649.htm",
}
# main-number count and inclusive max value per game
_RESULT_SPEC = {"lotto_max": (7, 50), "649": (6, 49)}

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _draw_date_strings(d: date) -> list[str]:
    mon = _MONTHS[d.month - 1]
    return [
        d.isoformat(),                       # 2026-06-26
        f"{mon} {d.day}, {d.year}",          # June 26, 2026
        f"{mon} {d.day:02d}, {d.year}",      # June 26, 2026 (padded)
        f"{mon[:3]} {d.day}, {d.year}",      # Jun 26, 2026
    ]


def draw_has_occurred(
    lottery_type: str, draw_date, *, buffer_minutes: int = 45, from_dt: datetime | None = None
) -> bool:
    """True once a draw's scheduled cutoff (+ a buffer) has passed in Pacific time."""
    if not valid_lottery_type(lottery_type):
        return False
    try:
        d = date.fromisoformat(draw_date) if isinstance(draw_date, str) else draw_date
    except Exception:
        return False
    sched = DRAW_SCHEDULE.get(lottery_type)
    if not sched:
        return False
    now = (from_dt or datetime.now(PT)).astimezone(PT)
    cutoff = datetime.combine(d, time(sched["hour"], sched["minute"]), PT) + timedelta(minutes=buffer_minutes)
    return now >= cutoff


def _parse_wclc_results(html: str, draw: date, main_count: int, max_n: int) -> dict | None:
    # Anchor on the draw date so we read the right draw, then pull ball numbers
    # (element text content like ">7<") that follow it.
    idx = -1
    for s in _draw_date_strings(draw):
        idx = html.find(s)
        if idx >= 0:
            idx += len(s)
            break
    if idx < 0:
        return None
    window = html[idx: idx + 1500]
    seq = [int(m.group(1)) for m in re.finditer(r">\s*0*(\d{1,2})\s*<", window)
           if 1 <= int(m.group(1)) <= max_n]
    main: list[int] = []
    for n in seq:
        if n not in main:
            main.append(n)
        if len(main) == main_count:
            break
    if len(main) != main_count:
        return None
    bonus = next((n for n in seq if n not in main), None)
    return {"numbers": main, "bonus": bonus, "draw_date": draw.isoformat()}


async def fetch_draw_results(lottery_type: str, draw_date) -> dict | None:
    """Fetch official winning numbers for a past draw, or None if unavailable.

    Returns {"numbers": [int...], "bonus": int|None, "draw_date": "YYYY-MM-DD"}.
    """
    spec = _RESULT_SPEC.get(lottery_type)
    url = WCLC_WINNING_URL.get(lottery_type)
    if not spec or not url:
        return None
    try:
        d = date.fromisoformat(draw_date) if isinstance(draw_date, str) else draw_date
    except Exception:
        return None
    main_count, max_n = spec
    try:
        async with httpx.AsyncClient(
            timeout=12.0, headers={"User-Agent": _USER_AGENT}, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return None
    return _parse_wclc_results(html, d, main_count, max_n)


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
