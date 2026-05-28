"""Canadian national lottery games — shared catalog for API and agreements."""

LOTTERY_TYPES: dict[str, dict] = {
    "lotto_max":   {"label": "Lotto Max",   "price": 6},
    "649":         {"label": "Lotto 6/49",  "price": 3},
    "daily_grand": {"label": "Daily Grand", "price": 3},
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
