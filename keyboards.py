"""Reusable inline keyboard builders."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Balance", callback_data="menu_balance"),
            InlineKeyboardButton("🎟 Participate", callback_data="menu_participate"),
        ],
        [
            InlineKeyboardButton("📋 My Tickets", callback_data="menu_tickets"),
            InlineKeyboardButton("🏆 History", callback_data="menu_history"),
        ],
        [
            InlineKeyboardButton("➕ Deposit", callback_data="menu_deposit"),
            InlineKeyboardButton("🔁 Transactions", callback_data="menu_transactions"),
        ],
        [
            InlineKeyboardButton("🔗 Invite Friend", callback_data="menu_invite"),
        ],
    ])


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 New Round", callback_data="admin_newround"),
            InlineKeyboardButton("🔒 Close Round", callback_data="admin_closeround"),
        ],
        [
            InlineKeyboardButton("🎲 Draw Winner", callback_data="admin_draw"),
            InlineKeyboardButton("📋 Round Info", callback_data="admin_roundinfo"),
        ],
        [
            InlineKeyboardButton("💵 Pending Deposits", callback_data="admin_deposits"),
            InlineKeyboardButton("👥 Members", callback_data="admin_members"),
        ],
    ])


def deposit_approval(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"dep_approve_{req_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"dep_reject_{req_id}"),
        ]
    ])


def confirm_action(action: str, data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{action}_{data}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ]
    ])


def back_button(target: str = "start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back", callback_data=f"back_{target}")]
    ])
