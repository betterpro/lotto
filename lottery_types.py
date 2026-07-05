"""Canadian national lottery games — shared catalog for API and agreements."""

import json

LOTTERY_TYPES: dict[str, dict] = {
    "lotto_max":   {"label": "Lotto Max",   "price": 6},
    "649":         {"label": "Lotto 6/49",  "price": 3},
    "daily_grand": {"label": "Daily Grand", "price": 3},
}

# Ticket number rows per game (keep in sync with mini_app/src/lottery.js)
# rows_per_ticket: how many printed lines make up one physical ticket / play —
# Lotto Max prints 3 lines per play, 6/49 1 line, Daily Grand 1 selection (main+grand).
TICKET_LAYOUTS: dict[str, dict] = {
    "lotto_max": {
        "label": "Lotto Max",
        "repeat_row": {"label": "Line", "count": 7, "min": 1, "max": 52},
        "min_rows": 1,
        "max_rows": 30,
        "rows_per_ticket": 3,
    },
    "649": {
        "label": "Lotto 6/49",
        "repeat_row": {"label": "Classic", "count": 6, "min": 1, "max": 49},
        "min_rows": 1,
        "max_rows": 30,
        "rows_per_ticket": 1,
    },
    "daily_grand": {
        "label": "Daily Grand",
        "rows": [
            {"label": "Main numbers", "count": 5, "min": 1, "max": 49},
            {"label": "Grand number", "count": 1, "min": 1, "max": 7},
        ],
        "rows_per_ticket": 2,
    },
}


def rows_per_ticket(lottery_type: str | None) -> int:
    """Printed lines that make up one physical ticket for this game."""
    layout = ticket_layout(lottery_type)
    rpt = layout.get("rows_per_ticket")
    if rpt:
        return int(rpt)
    if not is_variable_row_layout(layout):
        return max(1, len(layout.get("rows", [])))
    return 1


def count_tickets(rows: list, lottery_type: str | None) -> int:
    """Number of whole physical tickets represented by these lines (ceil)."""
    rpt = rows_per_ticket(lottery_type)
    n = len(rows or [])
    if rpt <= 0:
        return n
    return (n + rpt - 1) // rpt


def group_rows_into_tickets(rows: list, lottery_type: str | None) -> list[list]:
    """Split a flat list of lines into per-ticket chunks (rows_per_ticket each)."""
    rpt = rows_per_ticket(lottery_type)
    if rpt <= 1:
        return [[r] for r in (rows or [])]
    return [list(rows[i:i + rpt]) for i in range(0, len(rows or []), rpt)]

# Auto-participate preference prices (Profile settings)
LOTTERY_PREFERENCE_PRICES = {
    **{k: v["price"] for k, v in LOTTERY_TYPES.items()},
    "both": 9.0,  # Lotto Max + 6/49 combo
}


def lottery_label(lottery_type: str | None) -> str:
    key = lottery_type or ""
    if key in LOTTERY_TYPES:
        return LOTTERY_TYPES[key]["label"]
    return key.replace("_", " ").title() or "BCLC draw"


def lottery_share_price(lottery_type: str | None, *, default: float = 3.0) -> float:
    key = lottery_type or ""
    row = LOTTERY_TYPES.get(key)
    return float(row["price"]) if row else default


def valid_lottery_type(lottery_type: str | None) -> bool:
    return bool(lottery_type and lottery_type in LOTTERY_TYPES)


def ticket_layout(lottery_type: str | None) -> dict:
    key = lottery_type or "lotto_max"
    return TICKET_LAYOUTS.get(key, TICKET_LAYOUTS["lotto_max"])


def is_variable_row_layout(layout: dict) -> bool:
    return "repeat_row" in layout


def row_spec_for_index(layout: dict, index: int) -> dict:
    if is_variable_row_layout(layout):
        base = layout["repeat_row"]
        return {**base, "label": f"Line {index + 1}"}
    return layout["rows"][index]


def parse_ticket_numbers(raw) -> list[list]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return []
    else:
        data = raw
    if not isinstance(data, list) or not data:
        return []
    if isinstance(data[0], (int, float)):
        return [[int(n) for n in data]]
    return [
        [int(n) for n in row if isinstance(n, (int, float))]
        for row in data
        if isinstance(row, list)
    ]


def _clamp_row(values: list, spec: dict) -> list[int]:
    out = []
    for n in values:
        try:
            v = int(n)
        except (TypeError, ValueError):
            continue
        if spec["min"] <= v <= spec["max"]:
            out.append(v)
    return out[: spec["count"]]


def normalize_ticket_rows(numbers, lottery_type: str | None) -> list[list]:
    layout = ticket_layout(lottery_type)
    parsed = parse_ticket_numbers(numbers)

    if is_variable_row_layout(layout):
        spec = layout["repeat_row"]
        max_rows = layout.get("max_rows", 10)
        rows: list[list] = []
        for row in parsed:
            clamped = _clamp_row(row, spec)
            if len(clamped) == spec["count"]:
                rows.append(clamped)
        return rows[:max_rows]

    rows = []
    for i, spec in enumerate(layout["rows"]):
        src = parsed[i] if i < len(parsed) else []
        rows.append(_clamp_row(src, spec))
    return rows


def validate_ticket_rows(rows: list[list], lottery_type: str | None) -> bool:
    layout = ticket_layout(lottery_type)
    if not rows:
        return False

    if is_variable_row_layout(layout):
        spec = layout["repeat_row"]
        min_rows = layout.get("min_rows", 1)
        max_rows = layout.get("max_rows", 10)
        if not (min_rows <= len(rows) <= max_rows):
            return False
        return all(
            len(row) == spec["count"]
            and all(spec["min"] <= int(n) <= spec["max"] for n in row)
            for row in rows
        )

    if len(rows) != len(layout["rows"]):
        return False
    for spec, row in zip(layout["rows"], rows):
        if len(row) != spec["count"]:
            return False
        if not all(spec["min"] <= int(n) <= spec["max"] for n in row):
            return False
    return True


def format_ticket_numbers_message(rows: list[list], lottery_type: str | None) -> str:
    layout = ticket_layout(lottery_type)
    parts = []
    if is_variable_row_layout(layout):
        for i, row in enumerate(rows):
            nums = "  ".join(f"<b>{n}</b>" for n in row)
            parts.append(f"Line {i + 1}: {nums}")
    else:
        for spec, row in zip(layout["rows"], rows):
            nums = "  ".join(f"<b>{n}</b>" for n in row)
            parts.append(f"{spec['label']}: {nums}")
    return "\n".join(parts)


def parse_round_tickets(raw, lottery_type: str | None = None) -> list[dict]:
    """Parse rounds.round_tickets JSON: [{image, rows}, ...]."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return []
    else:
        data = raw
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows = normalize_ticket_rows(item.get("rows") or [], lottery_type)
        out.append({
            "image": item.get("image"),
            "rows": rows,
        })
    return out


def merge_round_ticket_rows(tickets: list[dict]) -> list[list]:
    rows: list[list] = []
    for t in tickets:
        rows.extend(t.get("rows") or [])
    return rows


# Auto-results: main-number count + minimum matches that win any prize tier.
# (Lotto Max 3/7 = free play; 6/49 2/6 = free play.) Daily Grand isn't auto-matched.
RESULT_GAMES = {
    "lotto_max": {"main_count": 7, "win_threshold": 3, "has_bonus": True},
    "649":       {"main_count": 6, "win_threshold": 2, "has_bonus": True},
}


def supports_auto_results(lottery_type: str | None) -> bool:
    return lottery_type in RESULT_GAMES


def match_lines(lottery_type, winning_main, bonus, lines) -> dict:
    """Match the pool's lines against official winning numbers.

    Returns per-line match counts, whether any line hit a paying tier, and a
    human label for the best line (e.g. "6/7 + bonus"). Cash amounts are not
    computed — the trustee confirms the actual prize.
    """
    cfg = RESULT_GAMES.get(lottery_type)
    main_count = cfg["main_count"] if cfg else len(winning_main or [])
    threshold = cfg["win_threshold"] if cfg else None
    wn = {int(x) for x in (winning_main or [])}
    b = int(bonus) if bonus not in (None, "") else None

    out = []
    best = (-1, False)  # (main_matches, bonus_matched) for ordering
    any_win = False
    for line in lines or []:
        nums = [int(x) for x in line if str(x).strip() != ""]
        main = sum(1 for n in nums if n in wn)
        bmatch = bool(b is not None and b in nums)
        win = threshold is not None and main >= threshold
        any_win = any_win or win
        if (main, bmatch) > best:
            best = (main, bmatch)
        out.append({"numbers": nums, "main_matches": main, "bonus_matched": bmatch, "win": win})

    best_main, best_bonus = (best if best[0] >= 0 else (0, False))
    best_label = f"{best_main}/{main_count}" + (" + bonus" if best_bonus else "")
    return {
        "lines": out,
        "any_win": any_win,
        "best_main": best_main,
        "best_bonus": best_bonus,
        "best_label": best_label,
        "main_count": main_count,
    }


def build_scan_prompt(lottery_type: str | None) -> str:
    layout = ticket_layout(lottery_type)

    # Shared rules — accuracy matters more than anything (real money rides on it).
    preamble = (
        "You are transcribing the player's chosen numbers from a photo of a Canadian "
        "lottery ticket. The photo is often ROTATED or SIDEWAYS — first mentally rotate "
        "it so the printed text reads upright, then read it. "
        "Numbers are printed zero-padded as two digits (04 = 4, 05 = 5); strip leading "
        "zeros. Read the digits EXACTLY as printed — do NOT guess, estimate, round, "
        "re-order, or invent any number. If you cannot clearly read a line, OMIT that "
        "line rather than fabricating it. Returning fewer correct lines is far better "
        "than returning made-up numbers. Never copy the numbers from the example below. "
    )

    if lottery_type == "649":
        return (
            preamble
            + "This is a Lotto 6/49 ticket. Read EVERY row under the CLASSIC DRAW section. "
            "Each classic row has exactly 6 numbers from 1 to 49. "
            "Do NOT include Gold Ball / ENCORE serial codes (long codes like 09533128-01). "
            "Return ONLY a JSON object, no extra text:\n"
            "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
            "- rows: array of arrays — one inner array per classic line, top to bottom, "
            "each with exactly 6 integers\n"
            'Example shape only: {"draw_date":"2026-05-27","rows":[[10,14,22,25,44,45],[5,10,12,27,32,42]]}'
        )

    if is_variable_row_layout(layout):
        spec = layout["repeat_row"]
        return (
            preamble
            + f"This is a {layout['label']} ticket. The player's selections are a block of "
            f"rows; read EVERY selection row, top to bottom — there may be 3, 4, 5 or more. "
            f"Each row has exactly {spec['count']} numbers from {spec['min']} to {spec['max']}. "
            "Ignore everything that is NOT a selection row: the game logo, the draw date, "
            "the word EXTRA and its 47-67-75-96 numbers, ENCORE, TOTAL/prices, the Wager ID, "
            "the Retailer number, and any long barcode or serial numbers. "
            "Return ONLY a JSON object, no extra text:\n"
            "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
            f"- rows: array of arrays — one inner array per selection row, each with exactly "
            f"{spec['count']} integers\n"
            'Example shape only: {"draw_date":"2026-06-26","rows":[[1,2,3,4,5,6,7],[8,9,10,11,12,13,14]]}'
        )

    row_lines = "\n".join(
        f"  - {r['label']}: exactly {r['count']} integers from {r['min']} to {r['max']}"
        for r in layout["rows"]
    )
    n = len(layout["rows"])
    return (
        preamble
        + f"This is a {layout['label']} ticket. Read ALL player selection lines visible. "
        "Return ONLY a JSON object, no extra text:\n"
        "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
        f"- rows: array of exactly {n} arrays (one per line below):\n{row_lines}\n"
        'Example shape only: {"draw_date":"2026-06-26","rows":[[3,14,22,31,38],[6]]}'
    )
