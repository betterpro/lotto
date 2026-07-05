"""Official prize tiers for Canadian lottery games (BCLC / WCLC / ILC).

Only the FIXED-amount tiers are deterministic and safe to auto-calculate:

  Lotto Max — 4/7 = $20, 3/7 + Bonus = $20, 3/7 = Free Play
  Lotto 6/49 (Classic) — 3/6 = $10, 2/6 + Bonus = $5, 2/6 = Free Play

Higher tiers (jackpot, 6/7, 5/7, 4/7+B for Max; 6/6, 5/6, 5/6+B, 4/6 for 6/49)
are pari-mutuel — the cash-per-winner is set per draw and published only in the
official prize breakdown. Those are returned as `variable=True` with amount None
so the trustee confirms the amount from the official result before accepting.

Each tier: (main_required, needs_bonus, label, fixed_amount|None, is_free_play, is_variable)
"""

PRIZE_TIERS: dict[str, list[tuple]] = {
    "lotto_max": [
        (7, False, "7/7",          None, False, True),   # jackpot (pari-mutuel)
        (6, True,  "6/7 + Bonus",  None, False, True),
        (6, False, "6/7",          None, False, True),
        (5, True,  "5/7 + Bonus",  None, False, True),
        (5, False, "5/7",          None, False, True),
        (4, True,  "4/7 + Bonus",  None, False, True),
        (4, False, "4/7",          20.0, False, False),   # fixed $20
        (3, True,  "3/7 + Bonus",  20.0, False, False),   # fixed $20
        (3, False, "3/7",          None, True,  False),   # free play
    ],
    "649": [
        (6, False, "6/6",          None, False, True),    # jackpot (pari-mutuel)
        (5, True,  "5/6 + Bonus",  None, False, True),
        (5, False, "5/6",          None, False, True),
        (4, False, "4/6",          None, False, True),
        (3, False, "3/6",          10.0, False, False),    # fixed $10
        (2, True,  "2/6 + Bonus",  5.0,  False, False),    # fixed $5
        (2, False, "2/6",          None, True,  False),    # free play
    ],
}


def supports_prize_calc(lottery_type: str | None) -> bool:
    return lottery_type in PRIZE_TIERS


def line_prize(lottery_type: str | None, main_matches: int, bonus_matched: bool) -> dict:
    """Best prize tier for a single line given its match counts.

    Returns {tier, amount, free, variable, win}. amount is a fixed CAD value,
    or None when the tier is pari-mutuel (variable=True) — the trustee confirms it.
    """
    for main, needs_bonus, label, amount, free, variable in PRIZE_TIERS.get(lottery_type or "", []):
        if main_matches == main and (bonus_matched if needs_bonus else True):
            return {
                "tier": label,
                "amount": amount,
                "free": free,
                "variable": variable,
                "win": True,
            }
    return {"tier": None, "amount": 0.0, "free": False, "variable": False, "win": False}


def calculate_line_prizes(lottery_type: str | None, matched_lines: list[dict]) -> list[dict]:
    """Annotate match_lines() output with the prize tier for each line.

    `matched_lines` items look like {numbers, main_matches, bonus_matched, win}.
    """
    out = []
    for ln in matched_lines or []:
        pz = line_prize(lottery_type, ln.get("main_matches", 0), bool(ln.get("bonus_matched")))
        out.append({
            "numbers": ln.get("numbers", []),
            "main_matches": ln.get("main_matches", 0),
            "bonus_matched": bool(ln.get("bonus_matched")),
            "tier": pz["tier"],
            "amount": pz["amount"] or 0.0,
            "free": pz["free"],
            "variable": pz["variable"],
            "win": pz["win"],
        })
    return out
