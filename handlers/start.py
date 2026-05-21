"""Registration and main-menu handlers."""

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import TRUSTEE_ID, CURRENCY
from keyboards import main_menu, admin_menu


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = ctx.bot_data["db"]

    # Parse referral: /start ref_<inviter_id>
    invited_by: int | None = None
    if ctx.args:
        arg = ctx.args[0]
        if arg.startswith("ref_"):
            try:
                invited_by = int(arg[4:])
            except ValueError:
                pass

    is_trustee = 1 if user.id == TRUSTEE_ID else 0
    existing = await db.get_user(conn, user.id)

    if not existing:
        await db.create_user(
            conn,
            telegram_id=user.id,
            username=user.username,
            full_name=user.full_name,
            invited_by=invited_by,
            is_trustee=is_trustee,
        )
        welcome = (
            f"👋 Welcome, *{user.first_name}*!\n\n"
            "You've been registered in the *Group Lottery*.\n"
            "Deposit credits, join weekly rounds, and win big! 🎉"
        )
    else:
        welcome = f"👋 Welcome back, *{user.first_name}*!"

    record = await db.get_user(conn, user.id)
    credit = record["credit"] if record else 0.0

    msg = (
        f"{welcome}\n\n"
        f"💰 *Balance:* {credit:.2f} {CURRENCY}\n\n"
        "Use the menu below to get started."
    )

    keyboard = admin_menu() if is_trustee else main_menu()
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = ctx.bot_data["db"]
    record = await db.get_user(conn, user.id)

    if not record:
        await update.message.reply_text(
            "Please start the bot first with /start"
        )
        return

    keyboard = admin_menu() if record["is_trustee"] else main_menu()
    await update.message.reply_text(
        "Choose an option:", reply_markup=keyboard
    )
