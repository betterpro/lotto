#!/usr/bin/env python3
"""Seed demo historical rounds (3 Lotto Max + 3 6/49) and renumber live rounds to #7/#8."""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Verified Canada draw data — March 2026 (~2 months before May 2026)
HISTORICAL = [
    {
        "id": 1,
        "lottery_type": "lotto_max",
        "draw_date": "2026-03-20",
        "jackpot": 50_000_000,
        "winning_numbers": [2, 14, 25, 31, 36, 41, 47],
        "bonus_number": 13,
        "ticket_numbers": [2, 14, 25, 31, 36, 41, 47],
        "price_per_share": 6.0,
        "tickets_target": 25,
        "total_prize": 0,
    },
    {
        "id": 2,
        "lottery_type": "lotto_max",
        "draw_date": "2026-03-27",
        "jackpot": 60_000_000,
        "winning_numbers": [5, 34, 37, 38, 48, 49, 50],
        "bonus_number": 9,
        "ticket_numbers": [5, 12, 37, 38, 44, 48, 49],
        "price_per_share": 6.0,
        "tickets_target": 25,
        "total_prize": 0,
    },
    {
        "id": 3,
        "lottery_type": "lotto_max",
        "draw_date": "2026-03-31",
        "jackpot": 65_000_000,
        "winning_numbers": [6, 11, 31, 38, 40, 46, 50],
        "bonus_number": 37,
        "ticket_numbers": [6, 11, 19, 31, 40, 46, 50],
        "price_per_share": 6.0,
        "tickets_target": 25,
        "total_prize": 463.10,  # Match 6 tier split (demo)
    },
    {
        "id": 4,
        "lottery_type": "649",
        "draw_date": "2026-03-14",
        "jackpot": 5_000_000,
        "winning_numbers": [9, 15, 16, 20, 38, 45],
        "bonus_number": 10,
        "ticket_numbers": [9, 15, 16, 20, 38, 45],
        "price_per_share": 3.0,
        "tickets_target": 25,
        "total_prize": 99.20,
    },
    {
        "id": 5,
        "lottery_type": "649",
        "draw_date": "2026-03-21",
        "jackpot": 5_000_000,
        "winning_numbers": [2, 16, 18, 37, 39, 41],
        "bonus_number": 47,
        "ticket_numbers": [2, 16, 18, 37, 39, 41],
        "price_per_share": 3.0,
        "tickets_target": 25,
        "total_prize": 110.50,
    },
    {
        "id": 6,
        "lottery_type": "649",
        "draw_date": "2026-03-28",
        "jackpot": 5_000_000,
        "winning_numbers": [10, 11, 25, 35, 37, 42],
        "bonus_number": 36,
        "ticket_numbers": [10, 11, 25, 35, 37, 42],
        "price_per_share": 3.0,
        "tickets_target": 25,
        "total_prize": 1273.00,
    },
]

DEMO_USERS = [
    (900_001, "alex_pool", "Alex Chen"),
    (900_002, "sam_lucky", "Sam Rivera"),
    (900_003, "jordan649", "Jordan Lee"),
    (900_004, "maya_tickets", "Maya Patel"),
    (900_005, "chris_draw", "Chris Nguyen"),
    (900_006, "taylor_max", "Taylor Kim"),
    (900_007, "riley_lotto", "Riley Brooks"),
    (900_008, "casey_bc", "Casey Walsh"),
    (900_009, "morgan_win", "Morgan Singh"),
    (900_010, "jamie_pool", "Jamie Foster"),
    (900_011, "drew_649", "Drew Martinez"),
]


def _ts(draw_date: str, days_before: int = 0, hour: int = 18) -> str:
    from datetime import date, datetime, timedelta

    d = date.fromisoformat(draw_date) - timedelta(days=days_before)
    return datetime(d.year, d.month, d.day, hour, 0, 0).strftime("%Y-%m-%d %H:%M:%S")


async def ensure_users(conn: asyncpg.Connection) -> list[int]:
    ids: list[int] = []
    rows = await conn.fetch("SELECT telegram_id FROM users ORDER BY telegram_id")
    ids.extend(r["telegram_id"] for r in rows)

    for tid, username, full_name in DEMO_USERS:
        if tid not in ids:
            await conn.execute(
                """
                INSERT INTO users (telegram_id, username, full_name, credit, is_trustee, created_at)
                VALUES ($1, $2, $3, 0, 0, to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))
                ON CONFLICT (telegram_id) DO NOTHING
                """,
                tid,
                username,
                full_name,
            )
            ids.append(tid)

    rows = await conn.fetch("SELECT telegram_id FROM users ORDER BY telegram_id")
    return [r["telegram_id"] for r in rows]


async def renumber_live_rounds(conn: asyncpg.Connection) -> None:
    """Move existing rounds #1 and #2 to temp IDs, then to #7 and #8 after seed inserts."""
    live = await conn.fetch(
        "SELECT id FROM rounds WHERE id IN (1, 2) ORDER BY id"
    )
    if not live:
        print("No rounds #1/#2 found — skipping renumber.")
        return

    mapping = {1: (90_001, 7), 2: (90_002, 8)}
    for old_id in [r["id"] for r in live]:
        temp_id, final_id = mapping[old_id]
        await conn.execute(
            "UPDATE participations SET round_id = $1 WHERE round_id = $2",
            temp_id,
            old_id,
        )
        await conn.execute("UPDATE rounds SET id = $1 WHERE id = $2", temp_id, old_id)
        print(f"  Staged round #{old_id} -> temp #{temp_id}")

    for temp_id, final_id in mapping.values():
        if await conn.fetchval("SELECT 1 FROM rounds WHERE id = $1", temp_id):
            await conn.execute(
                "UPDATE participations SET round_id = $1 WHERE round_id = $2",
                final_id,
                temp_id,
            )
            await conn.execute("UPDATE rounds SET id = $1 WHERE id = $2", final_id, temp_id)
            print(f"  Renumbered temp #{temp_id} -> round #{final_id}")


async def clear_historical_slots(conn: asyncpg.Connection) -> None:
    """Remove prior demo rounds 1–6 if re-running."""
    await conn.execute("DELETE FROM participations WHERE round_id BETWEEN 1 AND 6")
    await conn.execute("DELETE FROM rounds WHERE id BETWEEN 1 AND 6")


async def insert_historical(conn: asyncpg.Connection, user_ids: list[int]) -> None:
    rng = random.Random(42)
    trustee_id = int(os.environ.get("TRUSTEE_TELEGRAM_ID", "0") or 0)
    real_users = [u for u in user_ids if u < 900_000]
    demo_users = [u for u in user_ids if u >= 900_000]

    for rd in HISTORICAL:
        n = rng.randint(3, 11)
        pool_ids = demo_users if demo_users else user_ids
        picked = rng.sample(pool_ids, min(n, len(pool_ids)))

        # Always include the logged-in trustee on most demo rounds so the app shows your stake
        must = []
        if trustee_id in user_ids and rd["id"] in (1, 2, 3, 4, 6):
            must.append(trustee_id)
        elif real_users:
            must.append(real_users[0])

        participants = list(dict.fromkeys(must + picked))[:n]
        if len(participants) < 3 and len(pool_ids) >= 3:
            extras = [u for u in pool_ids if u not in participants]
            participants += rng.sample(extras, min(3 - len(participants), len(extras)))

        pool = 0.0
        parts: list[tuple] = []

        for uid in participants:
            shares = 2 if uid == trustee_id else rng.randint(1, 3)
            amount = round(shares * rd["price_per_share"], 2)
            pool += amount
            parts.append((uid, amount, shares))

        winner_id = rng.choice(participants) if rd["total_prize"] else None
        opened = _ts(rd["draw_date"], days_before=6, hour=12)
        closed = _ts(rd["draw_date"], days_before=1, hour=22)
        drawn = _ts(rd["draw_date"], days_before=0, hour=23)

        await conn.execute(
            """
            INSERT INTO rounds (
                id, status, pool, draw_date, winner_id, opened_at, closed_at, drawn_at,
                jackpot, tickets_target, price_per_share, winning_numbers, bonus_number,
                ticket_numbers, lottery_type
            ) OVERRIDING SYSTEM VALUE VALUES (
                $1, 'drawn', $2, $3, $4, $5, $6, $7,
                $8, $9, $10, $11, $12, $13, $14
            )
            """,
            rd["id"],
            pool,
            rd["draw_date"],
            winner_id,
            opened,
            closed,
            drawn,
            rd["jackpot"],
            rd["tickets_target"],
            rd["price_per_share"],
            json.dumps(rd["winning_numbers"]),
            rd["bonus_number"],
            json.dumps(rd["ticket_numbers"]),
            rd["lottery_type"],
        )

        for uid, amount, shares in parts:
            prize = 0.0
            if winner_id == uid and rd["total_prize"]:
                prize = round(rd["total_prize"] * (amount / pool), 2)
            await conn.execute(
                """
                INSERT INTO participations (round_id, user_id, amount, shares, prize, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (round_id, user_id) DO UPDATE
                SET amount = EXCLUDED.amount, shares = EXCLUDED.shares, prize = EXCLUDED.prize
                """,
                rd["id"],
                uid,
                amount,
                shares,
                prize,
                closed,
            )

        print(
            f"  Round #{rd['id']} {rd['lottery_type']} draw {rd['draw_date']} "
            f"jackpot ${rd['jackpot']:,} - {len(participants)} players - pool ${pool:.0f}"
        )


async def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(url)
    try:
        async with conn.transaction():
            print("Ensuring demo users...")
            user_ids = await ensure_users(conn)
            print(f"  {len(user_ids)} users available")

            print("Staging live rounds #1/#2...")
            live = await conn.fetch("SELECT id, status FROM rounds WHERE id IN (1, 2)")
            for r in live:
                print(f"  Found live round #{r['id']} ({r['status']})")

            # Move live rounds off ids 1–2 before insert
            for old_id in [1, 2]:
                if await conn.fetchval("SELECT 1 FROM rounds WHERE id = $1", old_id):
                    temp = 90_000 + old_id
                    await conn.execute(
                        "UPDATE participations SET round_id = $1 WHERE round_id = $2",
                        temp,
                        old_id,
                    )
                    await conn.execute("UPDATE rounds SET id = $1 WHERE id = $2", temp, old_id)

            print("Clearing old demo slots 1-6...")
            await clear_historical_slots(conn)

            print("Inserting historical rounds 1-6...")
            await insert_historical(conn, user_ids)

            print("Renumbering live rounds to #7 and #8...")
            for temp_id, final_id in [(90_001, 7), (90_002, 8)]:
                if await conn.fetchval("SELECT 1 FROM rounds WHERE id = $1", temp_id):
                    await conn.execute(
                        "UPDATE participations SET round_id = $1 WHERE round_id = $2",
                        final_id,
                        temp_id,
                    )
                    await conn.execute(
                        "UPDATE rounds SET id = $1 WHERE id = $2", final_id, temp_id
                    )
                    print(f"  Live round -> #{final_id}")

            await conn.execute(
                "SELECT setval(pg_get_serial_sequence('rounds', 'id'), (SELECT COALESCE(MAX(id), 1) FROM rounds))"
            )

        rows = await conn.fetch(
            "SELECT id, status, lottery_type, draw_date, jackpot, pool FROM rounds ORDER BY id"
        )
        print("\nAll rounds:")
        for r in rows:
            print(
                f"  #{r['id']} {r['status']:8} {r['lottery_type'] or '?':10} "
                f"draw={r['draw_date']} jackpot=${r['jackpot'] or 0:,} pool=${float(r['pool'] or 0):.0f}"
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
