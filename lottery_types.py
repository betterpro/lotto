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
        "rows": [
            {"label": "Line 1", "count": 7, "min": 1, "max": 52},
            {"label": "Line 2", "count": 7, "min": 1, "max": 52},
            {"label": "Line 3", "count": 7, "min": 1, "max": 52},
        ],
    },
    "649": {
        "label": "Lotto 6/49",
        "rows": [{"label": "6/49 numbers", "count": 6, "min": 1, "max": 49}],
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
    return [[int(n) for n in row if isinstance(n, (int, float))] for row in data if isinstance(row, list)]


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
    rows: list[list] = []
    for i, spec in enumerate(layout["rows"]):
        src = parsed[i] if i < len(parsed) else []
        rows.append(_clamp_row(src, spec))
    return rows


def validate_ticket_rows(rows: list[list], lottery_type: str | None) -> bool:
    layout = ticket_layout(lottery_type)
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
    for spec, row in zip(layout["rows"], rows):
        nums = "  ".join(f"<b>{n}</b>" for n in row)
        parts.append(f"{spec['label']}: {nums}")
    return "\n".join(parts)


def build_scan_prompt(lottery_type: str | None) -> str:
    layout = ticket_layout(lottery_type)
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
