"""Built-in Telegram notification templates.

Each message the bot sends is a named template with {placeholders}. Defaults are
defined here for operational lottery events. Group admins create separate
WHEN/THEN notification rules; these built-in messages are not editable.
Optional content is passed as whole '_line' vars so empty ones collapse away
cleanly.
"""

import re

# key -> {label, desc, default, sample}
NOTIF_TEMPLATES: dict[str, dict] = {
    "broadcast": {
        "label": "Trustee broadcast",
        "desc": "Wrapper around a message the trustee sends to all group members.",
        "default": "📢 <b>{group}</b>\n{message}",
        "sample": {"group": "Friday Office Pool", "message": "Hey team! A new round is live — jump in before the draw 🎉"},
    },
    "new_round": {
        "label": "New round opened",
        "desc": "Broadcast to the group when a new round goes live.",
        "default": (
            "🎟️✨ <b>NEW ROUND #{seq} IS LIVE!</b> ✨🎟️\n"
            "{jackpot_line}"
            "{draw_line}"
            "💸 <b>${price}/share</b> · {target}\n"
            "Grab your shares and let's win together! 🍀"
        ),
        "sample": {"seq": 7, "jackpot_line": "🏆 Jackpot: <b>$70M</b>\n",
                   "draw_line": "📅 Draw: <b>Fri Jun 26</b>\n", "price": "6", "target": "no ticket limit"},
    },
    "round_closing": {
        "label": "Closing-soon reminder",
        "desc": "Nudges members who haven't joined, 48h / 24h before entries close.",
        "default": (
            "{emoji} <b>Round #{rid} closes in ~{hours}h!</b>\n"
            "You're not in yet — add your shares before the draw locks{jp}. ⏳"
        ),
        "sample": {"emoji": "⏰", "rid": 12, "hours": 24, "jp": " · <b>$55M</b> jackpot"},
    },
    "round_closed_trustee": {
        "label": "Round closed (trustee)",
        "desc": "Tells the trustee to buy the physical ticket once a round closes.",
        "default": (
            "🎫 <b>Round #{rid} closed — time to buy the ticket!</b>\n"
            "Pool <b>${pool}</b> · {tickets} ticket{ticket_s} to purchase{draw}"
        ),
        "sample": {"rid": 12, "pool": "150", "tickets": 2, "ticket_s": "s", "draw": " · draw Fri Jun 26"},
    },
    "contribution": {
        "label": "Member contributed",
        "desc": "Lets the group know someone added to the pool.",
        "default": (
            "💸 <b>{name}</b> just jumped into Round #{rid}! 🙌\n"
            "Pool is now <b>${pool}</b> 📈"
        ),
        "sample": {"name": "Alex", "rid": 12, "pool": "150"},
    },
    "member_joined": {
        "label": "New member joined",
        "desc": "Welcomes a new member to the group and energizes the community.",
        "default": (
            "🎉 <b>{name} joined {group}!</b>\n"
            "We’re now <b>{member_count}</b> members strong — welcome to the crew! 🙌"
        ),
        "sample": {"name": "Alex", "group": "Friday Office Pool", "member_count": 14},
    },
    "invite_friends": {
        "label": "Invite your friends",
        "desc": "Prompts a newly joined member to grow the group using its invite link.",
        "default": (
            "🙌 <b>Welcome to {group}, {name}!</b>\n"
            "Lottery pools are more fun together. Invite your friends to join the group:\n"
            "{invite_link}\n"
            "Join code: <code>{join_code}</code>"
        ),
        "sample": {
            "name": "Alex", "group": "Friday Office Pool",
            "invite_link": "https://t.me/LottoCheeBot?startapp=join_friday-office-pool",
            "join_code": "CHEE-4821",
        },
    },
    "contribution_momentum": {
        "label": "Contribution momentum",
        "desc": "Encourages members who have not added shares after activity in an open round.",
        "default": (
            "🔥 <b>{name} just added shares to {lotto_name} Round #{rid}!</b>\n"
            "The pool is now <b>${pool}</b>. Keep the momentum going with a "
            "<b>${price}</b> share when you’re ready. 🍀"
        ),
        "sample": {
            "name": "Alex", "lotto_name": "Lotto Max", "rid": 12,
            "pool": "150", "price": "5",
        },
    },
    "auto_joined": {
        "label": "Auto-joined a round",
        "desc": "Confirms an auto-participate entry was placed.",
        "default": (
            "🤖🎟️ <b>You're in Round #{rid}!</b>\n"
            "{shares} share{share_s} · <b>${amount}</b> deducted\n"
            "💰 Balance: ${balance} · good luck! 🍀"
        ),
        "sample": {"rid": 12, "shares": 2, "share_s": "s", "amount": "12.00", "balance": "38.00"},
    },
    "auto_join_skipped": {
        "label": "Auto-join skipped (low balance)",
        "desc": "Warns a member their auto-join was skipped for low balance.",
        "default": (
            "⚠️ <b>Auto-join skipped — Round #{rid}</b>\n"
            "Balance <b>${balance}</b> is below the <b>${needed}</b> needed.\n"
            "Top up to stay in the next draw! 🎟️"
        ),
        "sample": {"rid": 12, "balance": "3.00", "needed": "6.00"},
    },
    "etransfer_received": {
        "label": "E-transfer credited",
        "desc": "Confirms an e-transfer deposit was credited.",
        "default": (
            "✅💰 <b>${amount} added to your balance!</b>\n"
            "Your e-transfer landed — you're ready to play. 🎉"
        ),
        "sample": {"amount": "50.00"},
    },
    "ticket_purchased": {
        "label": "Ticket purchased",
        "desc": "Confirms the official ticket numbers were bought for the round.",
        "default": (
            "✅🎫 <b>Ticket locked in — Round #{rid}!</b>\n"
            "🎱 Your numbers: {numbers}"
        ),
        "sample": {"rid": 12, "numbers": "<b>4</b> <b>11</b> <b>19</b> <b>24</b> <b>31</b> <b>38</b> <b>47</b>"},
    },
    "draw_reminder": {
        "label": "Draw-date reminder line",
        "desc": "Appended after the ticket confirmation when reminders are on.",
        "default": "📅 Draw day: <b>{draw}</b> — fingers crossed! 🤞🍀",
        "sample": {"draw": "Fri Jun 26"},
    },
    "free_tickets": {
        "label": "Free tickets applied",
        "desc": "Member auto-enrolled with free shares from a previous win.",
        "default": (
            "🎁🎟️ <b>Free shares applied — Round #{seq}!</b>\n"
            "You got <b>{shares}</b> free share{share_s} from the last {game} win — "
            "no charge. Enjoy the ride! 🚀"
        ),
        "sample": {"seq": 7, "shares": 2, "share_s": "s", "game": "Lotto Max"},
    },
    "results_auto_win": {
        "label": "Results — pool won (auto)",
        "desc": "Auto-detected win after fetching official numbers.",
        "default": (
            "🎉🍀 <b>WE'VE GOT A WINNER — Round #{seq}!</b> 🍀🎉\n"
            "🎱 Winning numbers: {numbers}{bonus}\n"
            "Your pool hit <b>{best}</b> — that's a prize tier! 🏆\n"
            "Your trustee will confirm your share. 💰"
        ),
        "sample": {"seq": 7, "numbers": "<b>4</b> <b>5</b> <b>21</b> <b>35</b> <b>38</b> <b>45</b> <b>46</b>",
                   "bonus": " · bonus <b>13</b>", "best": "6/7 + bonus"},
    },
    "results_auto_nowin": {
        "label": "Results — no win (auto)",
        "desc": "Auto-detected result with no prize tier.",
        "default": (
            "📣 <b>Results are in — Round #{seq}</b>\n"
            "🎱 Winning numbers: {numbers}{bonus}\n"
            "Best line matched {best} — no prize this time. We'll get the next one! 🍀"
        ),
        "sample": {"seq": 7, "numbers": "<b>4</b> <b>5</b> <b>21</b> <b>35</b> <b>38</b> <b>45</b> <b>46</b>",
                   "bonus": " · bonus <b>13</b>", "best": "2/7"},
    },
    "you_won": {
        "label": "You won (final payout)",
        "desc": "Sent to a winner when the trustee finalizes the prize.",
        "default": (
            "🏆🎉 <b>YOU WON — Round #{rid}!</b> 🎉🏆\n"
            "{prize_line}"
            "{ft_line}"
            "🎱 Winning numbers: {numbers}\n"
            "{credited_line}"
        ),
        "sample": {"rid": 12, "prize_line": "💵 Cash prize: <b>$38.40</b> (your 1.2% share)\n",
                   "ft_line": "", "numbers": "<b>4</b> <b>5</b> <b>21</b> <b>35</b> <b>38</b> <b>45</b> <b>46</b>",
                   "credited_line": "✅ Credited straight to your balance! 💰"},
    },
    "results_no_prize": {
        "label": "Results — no prize (final)",
        "desc": "Sent to non-winning participants when results are finalized.",
        "default": (
            "🎟️ <b>Results — Round #{rid}</b>\n"
            "🎱 Winning numbers: {numbers}\n"
            "Your stake: ${stake} ({pct}%) — no luck this time. Onto the next draw! 🍀"
        ),
        "sample": {"rid": 12, "numbers": "<b>4</b> <b>5</b> <b>21</b> <b>35</b> <b>38</b> <b>45</b> <b>46</b>",
                   "stake": "6.00", "pct": "1.2"},
    },
}


# Human descriptions for the {placeholders} that appear in templates.
VAR_HELP: dict[str, str] = {
    "rid": "round number",
    "seq": "round number",
    "pool": "current pool total ($)",
    "name": "member's name",
    "amount": "amount ($)",
    "balance": "member's balance after ($)",
    "needed": "amount needed ($)",
    "shares": "number of shares",
    "share_s": "'s' when plural, else empty",
    "ticket_s": "'s' when plural, else empty",
    "tickets": "number of tickets to buy",
    "price": "price per share ($)",
    "target": "group pool target text; members still buy shares, not tickets",
    "lotto_name": "lottery name, for example Lotto Max or Lotto 6/49",
    "game": "lottery game name",
    "numbers": "winning / ticket numbers",
    "bonus": "bonus number suffix",
    "best": "best matched tier (e.g. 6/7)",
    "hours": "hours before the draw",
    "emoji": "⏰ / ⏳ urgency icon",
    "jp": "jackpot suffix",
    "jackpot_line": "jackpot line (auto, may be empty)",
    "draw_line": "draw-date line (auto, may be empty)",
    "draw": "draw date",
    "prize_line": "cash-prize line (auto, may be empty)",
    "ft_line": "free-tickets line (auto, may be empty)",
    "credited_line": "credited line (auto, may be empty)",
    "stake": "member's stake ($)",
    "pct": "member's share (%)",
    "group": "group name",
    "message": "the message the trustee typed",
    "member_count": "current number of members in the group",
    "invite_link": "shareable Telegram group invite link",
    "join_code": "group join code",
}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def describe_vars(text: str) -> list[dict]:
    """List the {placeholders} used in a template, with human descriptions."""
    seen = []
    for m in _PLACEHOLDER_RE.finditer(text or ""):
        name = m.group(1)
        if name not in [v["name"] for v in seen]:
            seen.append({"name": name, "help": VAR_HELP.get(name, "")})
    return seen


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def render_template(text: str, vars: dict) -> str:
    """Format a template, tolerating missing placeholders, and collapse blank
    lines left by empty optional vars."""
    try:
        out = text.format_map(_SafeDict(vars or {}))
    except Exception:
        out = text
    out = re.sub(r"\n[ \t]*\n+", "\n", out)
    return out.strip("\n")
