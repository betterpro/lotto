"""Next draw dates and estimated jackpots for Canadian national lottery games."""

from __future__ import annotations

import json
import re
import time as _time
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

import config
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

# Look like a real browser — the lottery sites return 403 to obvious bot clients,
# which is what made auto-results fail. Send full browser headers.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Cache-Control": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

# Result pages to try, in order, per game. WCLC covers the western provinces;
# PlayNow (BCLC) is where BC players see the same national draw results.
RESULT_SOURCES = {
    "lotto_max": [
        "https://www.wclc.com/games/lotto-max.htm",
        "https://www.playnow.com/lottery/lotto-max/",
    ],
    "649": [
        "https://www.wclc.com/games/lotto-649.htm",
        "https://www.playnow.com/lottery/lotto-649/",
    ],
}


async def _fetch_html(url: str) -> str | None:
    """GET a page with browser headers; return text or None on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=15.0, headers=_BROWSER_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception:
        return None


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

    html = await _fetch_html(url)
    if not html:
        return None
    return _parse_wclc_jackpot_millions(html, section)


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


def hours_until_draw(lottery_type: str, draw_date, *, from_dt: datetime | None = None) -> float | None:
    """Hours from now until the draw's cutoff (Pacific). Negative if passed."""
    try:
        d = date.fromisoformat(draw_date) if isinstance(draw_date, str) else draw_date
    except Exception:
        return None
    if not d:
        return None
    sched = DRAW_SCHEDULE.get(lottery_type) or {"hour": 19, "minute": 30}
    now = (from_dt or datetime.now(PT)).astimezone(PT)
    cutoff = datetime.combine(d, time(sched["hour"], sched["minute"]), PT)
    return (cutoff - now).total_seconds() / 3600.0


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


# --- Apify actor results source (preferred when configured) ------------------
# The lottery sites block server requests (403); an Apify actor runs a real
# browser and returns structured draws. Configure APIFY_TOKEN (+ optional actor
# and input JSON). Field names vary between actors, so parsing is flexible.

_GAME_ALIASES = {
    "lotto_max": ["lotto max", "lottomax", "lotto-max", "maxmillions", "max millions"],
    "649": ["6/49", "649", "6-49", "lotto 6/49", "lotto649", "lotto 649"],
    "daily_grand": ["daily grand", "dailygrand", "daily-grand", "grand"],
}
_GAME_KEYS = ("game", "lottery", "name", "title", "drawName", "product", "gameName", "type")
_DATE_KEYS = ("draw_date", "drawDate", "date", "drawdate", "draw_date_iso", "drawTime")
_NUM_KEYS = ("numbers", "winningNumbers", "winning_numbers", "mainNumbers",
             "main_numbers", "results", "balls", "numbersDrawn")
_BONUS_KEYS = ("bonus", "bonusNumber", "bonus_number", "bonusBall", "bonus_ball")

# Cache the actor's dataset for a short window — a run returns many draws and
# actor runs cost time/credits, so reuse them across lookups.
_APIFY_CACHE_TTL = 900  # 15 min
_apify_cache: dict = {"at": 0.0, "items": None}


def _to_iso_date(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):  # epoch seconds or ms
        try:
            secs = val / 1000 if val > 1e12 else val
            return datetime.utcfromtimestamp(secs).date().isoformat()
        except Exception:
            return None
    s = str(val).strip()
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    for mon_i, mon in enumerate(_MONTHS, start=1):
        for token in (mon, mon[:3]):
            m = re.search(rf"{token}\.?\s+(\d{{1,2}}),?\s+(20\d{{2}})", s, re.IGNORECASE)
            if m:
                try:
                    return date(int(m.group(2)), mon_i, int(m.group(1))).isoformat()
                except ValueError:
                    return None
    return None


def _first(item: dict, keys) -> object:
    for k in keys:
        if k in item and item[k] not in (None, "", []):
            return item[k]
    return None


def _extract_numbers(val, max_n: int) -> list[int]:
    raw = val
    if isinstance(raw, (int, float)):
        raw = [raw]
    elif isinstance(raw, str):
        raw = re.findall(r"\d{1,2}", raw)
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for n in raw:
        try:
            v = int(n)
        except (TypeError, ValueError):
            continue
        if 1 <= v <= max_n:
            out.append(v)
    return out


def _match_apify_item(item, lottery_type, draw_iso, main_count, max_n) -> dict | None:
    if not isinstance(item, dict):
        return None
    game_text = " ".join(str(item.get(k, "")) for k in _GAME_KEYS).lower()
    aliases = _GAME_ALIASES.get(lottery_type, [])
    if aliases and not any(a in game_text for a in aliases):
        return None
    if _to_iso_date(_first(item, _DATE_KEYS)) != draw_iso:
        return None
    nums = _extract_numbers(_first(item, _NUM_KEYS), max_n)
    main = []
    for n in nums:
        if n not in main:
            main.append(n)
        if len(main) == main_count:
            break
    if len(main) != main_count:
        return None
    bonus_val = _first(item, _BONUS_KEYS)
    bonus = None
    if bonus_val is not None:
        b = _extract_numbers(bonus_val, max_n)
        bonus = b[0] if b else None
    if bonus is None:
        bonus = next((n for n in nums if n not in main), None)
    return {"numbers": main, "bonus": bonus, "draw_date": draw_iso}


async def _apify_draw_items() -> list | None:
    """Run the configured Apify lottery actor and return its dataset items."""
    token = config.APIFY_TOKEN
    if not token:
        return None
    now = _time.monotonic()
    if _apify_cache["items"] is not None and (now - _apify_cache["at"]) < _APIFY_CACHE_TTL:
        return _apify_cache["items"]
    actor = (config.APIFY_LOTTERY_ACTOR or "eternal_ngultrum~lottery-draws").replace("/", "~")
    try:
        inp = json.loads(config.APIFY_LOTTERY_INPUT) if config.APIFY_LOTTERY_INPUT.strip() else {}
    except (ValueError, TypeError):
        inp = {}
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=inp)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None
    items = data if isinstance(data, list) else None
    _apify_cache["items"] = items
    _apify_cache["at"] = now
    return items


async def fetch_draw_results_apify(lottery_type: str, draw_iso: str, main_count: int, max_n: int) -> dict | None:
    items = await _apify_draw_items()
    if not items:
        return None
    for item in items:
        parsed = _match_apify_item(item, lottery_type, draw_iso, main_count, max_n)
        if parsed:
            return parsed
    return None


async def fetch_draw_results(lottery_type: str, draw_date) -> dict | None:
    """Fetch official winning numbers for a past draw, or None if unavailable.

    Returns {"numbers": [int...], "bonus": int|None, "draw_date": "YYYY-MM-DD"}.
    Prefers the Apify actor (when configured), then falls back to WCLC / PlayNow.
    """
    spec = _RESULT_SPEC.get(lottery_type)
    if not spec:
        return None
    try:
        d = date.fromisoformat(draw_date) if isinstance(draw_date, str) else draw_date
    except Exception:
        return None
    main_count, max_n = spec

    # 1) Apify actor (structured, bypasses the sites' bot blocking).
    apify = await fetch_draw_results_apify(lottery_type, d.isoformat(), main_count, max_n)
    if apify:
        return apify

    # 2) Direct scrape of WCLC, then PlayNow. The parser anchors on the draw date
    # and only returns a result when the exact expected count of in-range numbers
    # is found, so a source without this draw is skipped rather than misread.
    sources = RESULT_SOURCES.get(lottery_type) or [WCLC_WINNING_URL.get(lottery_type)]
    for url in sources:
        if not url:
            continue
        html = await _fetch_html(url)
        if not html:
            continue
        parsed = _parse_wclc_results(html, d, main_count, max_n)
        if parsed:
            return parsed
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
