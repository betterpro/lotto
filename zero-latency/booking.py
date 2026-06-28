"""Domain config + scheduling logic for Zero Latency VR Richmond.

Everything a non-developer is likely to tweak — the venue, opening hours, the
experiences and their prices — lives here.
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

import config

# ── Venue ────────────────────────────────────────────────────────────────────
VENUE = {
    "id": "richmond-city",
    "name": "Richmond City",
    "brand": "ZERO LATENCY VR",
    "tagline": "Free-roam virtual reality. Up to 8 players. One unforgettable mission.",
    "timezone": "America/Vancouver",
    "address": "Richmond, BC",
    # Opening hours per ISO weekday (1=Mon … 7=Sun): (open "HH:MM", close "HH:MM").
    # Sessions start from `open` up to (close − experience duration).
    "hours": {
        1: ("12:00", "21:00"),
        2: ("12:00", "21:00"),
        3: ("12:00", "21:00"),
        4: ("12:00", "22:00"),
        5: ("10:00", "23:00"),
        6: ("10:00", "23:00"),
        7: ("10:00", "21:00"),
    },
    "slot_interval": 30,        # minutes between session start times
    "arenas": 1,                # concurrent sessions the venue can run
    "booking_horizon_days": 30, # how far ahead guests may book
}

VENUE_TZ = ZoneInfo(VENUE["timezone"])
CURRENCY = config.CURRENCY

# ── Experiences ──────────────────────────────────────────────────────────────
# Posters render from accent/emoji/tag client-side, so there are no image assets
# to host and nothing can break.
EXPERIENCES = [
    {
        "id": "outbreak", "name": "Outbreak", "tag": "Zombie Survival", "emoji": "🧟",
        "accent": "#16a34a", "duration_min": 50, "min_players": 1, "max_players": 8,
        "price": 5900, "intensity": "Intense", "min_age": 13,
        "summary": "Fight your way out of a zombie-infested megacity in our most popular free-roam mission.",
    },
    {
        "id": "sol-raiders", "name": "Sol Raiders", "tag": "Competitive PvP", "emoji": "⚔️",
        "accent": "#f59e0b", "duration_min": 30, "min_players": 2, "max_players": 8,
        "price": 4900, "intensity": "Moderate", "min_age": 13,
        "summary": "Two teams, three arenas, one trophy. Capture the relays and outgun your rivals.",
    },
    {
        "id": "engineerium", "name": "Engineerium", "tag": "Exploration", "emoji": "🪐",
        "accent": "#8b5cf6", "duration_min": 30, "min_players": 1, "max_players": 8,
        "price": 4900, "intensity": "Relaxed", "min_age": 8,
        "summary": "A gravity-bending walk through an impossible alien world. Perfect for first-timers.",
    },
    {
        "id": "far-cry-vr", "name": "Far Cry VR: Dive Into Insanity", "tag": "Action Shooter", "emoji": "🌴",
        "accent": "#ef4444", "duration_min": 45, "min_players": 1, "max_players": 8,
        "price": 5900, "intensity": "Intense", "min_age": 16,
        "summary": "Escape Hope County's deadly cult across a sprawling tropical battleground.",
    },
    {
        "id": "undead-arena", "name": "Undead Arena", "tag": "Game Show Horror", "emoji": "🎯",
        "accent": "#06b6d4", "duration_min": 40, "min_players": 1, "max_players": 8,
        "price": 5500, "intensity": "Moderate", "min_age": 13,
        "summary": "Become a contestant in a televised zombie blood-sport. Score points, stay alive.",
    },
    {
        "id": "singularity", "name": "Singularity", "tag": "Sci-Fi Shooter", "emoji": "🤖",
        "accent": "#3b82f6", "duration_min": 30, "min_players": 1, "max_players": 8,
        "price": 4900, "intensity": "Intense", "min_age": 13,
        "summary": "A rogue AI has overrun the station. Fight room to room to shut it down.",
    },
]

EXPERIENCE_BY_ID = {e["id"]: e for e in EXPERIENCES}


# ── Helpers ──────────────────────────────────────────────────────────────────
def now_venue() -> datetime:
    return datetime.now(VENUE_TZ)


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def gen_ref() -> str:
    alphabet = (string.ascii_uppercase + string.digits)
    for ch in "O0I1":
        alphabet = alphabet.replace(ch, "")
    return "ZL-" + "".join(secrets.choice(alphabet) for _ in range(6))


def experience_public(e: dict) -> dict:
    return {
        "id": e["id"], "name": e["name"], "tag": e["tag"], "emoji": e["emoji"],
        "accent": e["accent"], "duration_min": e["duration_min"],
        "min_players": e["min_players"], "max_players": e["max_players"],
        "price": e["price"], "price_display": f"${e['price'] / 100:.0f}",
        "intensity": e["intensity"], "min_age": e["min_age"], "summary": e["summary"],
        "currency": CURRENCY,
    }


def slots_for(experience: dict, day_iso: str) -> list[time]:
    d = date.fromisoformat(day_iso)
    hours = VENUE["hours"].get(d.isoweekday())
    if not hours:
        return []
    open_t, close_t = parse_hhmm(hours[0]), parse_hhmm(hours[1])
    interval = VENUE["slot_interval"]
    dur = experience["duration_min"]
    cursor = datetime.combine(d, open_t)
    last_start = datetime.combine(d, close_t) - timedelta(minutes=dur)
    out: list[time] = []
    while cursor <= last_start:
        out.append(cursor.time())
        cursor += timedelta(minutes=interval)
    return out


def capacity(experience: dict) -> int:
    return experience["max_players"] * VENUE["arenas"]
