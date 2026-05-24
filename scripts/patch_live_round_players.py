#!/usr/bin/env python3
"""Add demo players to open live rounds #7 and #8."""
from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEMO_IDS = list(range(900_001, 900_012))


async def main() -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    trustee_id = int(os.environ["TRUSTEE_TELEGRAM_ID"])
    rng = random.Random(7)

    try:
        async with conn.transaction():
            for rid in (7, 8):
                row = await conn.fetchrow(
                    "SELECT price_per_share, closed_at FROM rounds WHERE id = $1 AND status = 'open'",
                    rid,
                )
                if not row:
                    print(f"Round #{rid}: skip (not open)")
                    continue

                price = float(row["price_per_share"])
                existing = await conn.fetchval(
                    "SELECT COUNT(*) FROM participations WHERE round_id = $1", rid
                )
                if existing >= 3:
                    print(f"Round #{rid}: already has {existing} players")
                    continue

                n = rng.randint(5, 9)
                picks = rng.sample(DEMO_IDS, min(n, len(DEMO_IDS)))
                if trustee_id not in picks:
                    picks = picks[: max(1, n - 1)] + [trustee_id]

                added = 0.0
                for uid in picks:
                    if await conn.fetchval(
                        "SELECT 1 FROM participations WHERE round_id = $1 AND user_id = $2",
                        rid,
                        uid,
                    ):
                        continue
                    shares = rng.randint(1, 3)
                    amount = round(shares * price, 2)
                    await conn.execute(
                        """
                        INSERT INTO participations (round_id, user_id, amount, shares)
                        VALUES ($1, $2, $3, $4)
                        """,
                        rid,
                        uid,
                        amount,
                        shares,
                    )
                    added += amount

                if added:
                    await conn.execute(
                        "UPDATE rounds SET pool = pool + $1 WHERE id = $2", added, rid
                    )

                cnt = await conn.fetchval(
                    "SELECT COUNT(*) FROM participations WHERE round_id = $1", rid
                )
                pool = await conn.fetchval("SELECT pool FROM rounds WHERE id = $1", rid)
                print(f"Round #{rid}: {cnt} players, pool ${float(pool or 0):.0f}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
