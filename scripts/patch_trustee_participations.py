#!/usr/bin/env python3
"""Add trustee/real-user participations to existing demo rounds 1-6."""
from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ROUNDS = [1, 2, 3, 4, 5, 6]


async def main() -> None:
    url = os.environ["DATABASE_URL"]
    trustee_id = int(os.environ["TRUSTEE_TELEGRAM_ID"])

    conn = await asyncpg.connect(url)
    try:
        async with conn.transaction():
            for rid in ROUNDS:
                row = await conn.fetchrow(
                    "SELECT price_per_share, pool FROM rounds WHERE id = $1", rid
                )
                if not row:
                    continue

                exists = await conn.fetchval(
                    "SELECT 1 FROM participations WHERE round_id = $1 AND user_id = $2",
                    rid,
                    trustee_id,
                )
                if exists:
                    print(f"  Round #{rid}: trustee already joined")
                    continue

                shares = random.choice([1, 2, 3])
                amount = round(shares * float(row["price_per_share"]), 2)
                closed = await conn.fetchval(
                    "SELECT closed_at FROM rounds WHERE id = $1", rid
                )

                await conn.execute(
                    """
                    INSERT INTO participations (round_id, user_id, amount, shares, prize, created_at)
                    VALUES ($1, $2, $3, $4, 0, COALESCE($5, to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')))
                    """,
                    rid,
                    trustee_id,
                    amount,
                    shares,
                    closed,
                )
                await conn.execute(
                    "UPDATE rounds SET pool = pool + $1 WHERE id = $2",
                    amount,
                    rid,
                )
                print(f"  Round #{rid}: added trustee {shares} shares (${amount})")

        rows = await conn.fetch(
            """
            SELECT r.id, p.shares, p.amount, p.prize,
                   (SELECT COUNT(*) FROM participations WHERE round_id = r.id) AS players
            FROM rounds r
            LEFT JOIN participations p ON p.round_id = r.id AND p.user_id = $1
            WHERE r.id BETWEEN 1 AND 6
            ORDER BY r.id
            """,
            trustee_id,
        )
        print("\nTrustee view on demo rounds:")
        for r in rows:
            print(
                f"  #{r['id']} shares={r['shares'] or '-'} stake=${float(r['amount'] or 0):.0f} "
                f"prize=${float(r['prize'] or 0):.0f} players={r['players']}"
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
