"""Canadian national lottery games — shared catalog for API and agreements."""

import json

LOTTERY_TYPES: dict[str, dict] = {
    "lotto_max":   {"label": "Lotto Max",   "price": 6},
    "649":         {"label": "Lotto 6/49",  "price": 3},
    "daily_grand": {"label": "Daily Grand", "price": 3},
}

# Ticket number rows per game (keep in sync with mini_app/src/lottery.js)
TICKET_LAYOUTS: dict[str, dict] = {
    "lotto_max": {
        "label": "Lotto Max",
        "repeat_row": {"label": "Line", "count": 7, "min": 1, "max": 52},
        "min_rows": 1,
        "max_rows": 10,
    },
    "649": {
        "label": "Lotto 6/49",
        "repeat_row": {"label": "Classic", "count": 6, "min": 1, "max": 49},
        "min_rows": 1,
        "max_rows": 10,
    },
    "daily_grand": {
        "label": "Daily Grand",
        "rows": [
            {"label": "Main numbers", "count": 5, "min": 1, "max": 49},
            {"label": "Grand number", "count": 1, "min": 1, "max": 7},
        ],
    },
}

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


def build_scan_prompt(lottery_type: str | None) -> str:
    layout = ticket_layout(lottery_type)

    if lottery_type == "649":
        return (
            "This is a Canadian Lotto 6/49 lottery ticket. "
            "Extract EVERY horizontal row under the CLASSIC DRAW section. "
            "Each classic row has exactly 6 main numbers from 1 to 49 (ignore leading zeros, e.g. 05 → 5). "
            "Do NOT include Gold Ball Draw serial codes (10-digit codes like 09533128-01). "
            "Return ONLY a JSON object with no extra text:\n"
            "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
            "- rows: array of arrays — one inner array per classic draw line, top to bottom, "
            "each with exactly 6 integers\n"
            'Example: {"draw_date":"2026-05-27","rows":[[10,14,22,25,44,45],[5,10,12,27,32,42],[13,14,27,35,41,45]]}'
        )

    if is_variable_row_layout(layout):
        spec = layout["repeat_row"]
        return (
            f"This is a Canadian {layout['label']} lottery ticket. "
            f"Extract EVERY horizontal player selection line on the ticket — there may be "
            f"3, 4, or more lines, so read them ALL, top to bottom. "
            f"Each line has exactly {spec['count']} numbers from {spec['min']} to {spec['max']} "
            "(ignore leading zeros, e.g. 05 → 5). "
            "Ignore barcodes, long serial/encore codes, prices, and the draw-date text. "
            "Return ONLY a JSON object with no extra text:\n"
            "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
            f"- rows: array of arrays — one inner array per selection line, "
            f"each with exactly {spec['count']} integers\n"
            f'Example: {{"draw_date":"2025-03-14","rows":'
            f'[[3,14,22,31,38,45,49],[1,12,13,14,15,16,17],[8,9,10,11,12,13,14],[2,7,19,28,33,40,51]]}}'
        )

    row_lines = "\n".join(
        f"  - {r['label']}: exactly {r['count']} integers from {r['min']} to {r['max']}"
        for r in layout["rows"]
    )
    n = len(layout["rows"])
    return (
        f"This is a Canadian {layout['label']} lottery ticket. "
        "Extract ALL player selection lines visible on the ticket. "
        "Return ONLY a JSON object with no extra text:\n"
        "- draw_date: the draw date as YYYY-MM-DD (null if not visible)\n"
        f"- rows: array of exactly {n} arrays (one per line below):\n{row_lines}\n"
        'Example: {"draw_date":"2025-03-14","rows":[[3,14,22,31,38,45,49],[1,12,13,14,15,16,17],[8,9,10,11,12,13,14]]}'
    )
