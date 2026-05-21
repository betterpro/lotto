"""
Group Lottery Telegram Bot
--------------------------
Start:   python bot.py
Requires .env with BOT_TOKEN and TRUSTEE_TELEGRAM_ID set.
"""

import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import database as db
from config import BOT_TOKEN
from keyboards import main_menu, admin_menu

from handlers.start import cmd_start, cmd_menu
from handlers.credit import (
    show_balance,
    show_transactions,
    handle_deposit_decision,
    build_deposit_conversation,
)
from handlers.lottery import (
    show_round,
    show_my_tickets,
    show_history,
    show_invite,
    build_participate_conversation,
)
from handlers.admin import (
    cmd_newround,
    cmd_closeround,
    cmd_roundinfo,
    cmd_deposits,
    cmd_members,
    build_draw_conversation,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Inline-button router
# ──────────────────────────────────────────────

async def callback_router(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Deposit approval / rejection handled elsewhere (registered first)
    if data.startswith("dep_"):
        return await handle_deposit_decision(update, ctx)

    routing = {
        # Member menu
        "menu_balance":      show_balance,
        "menu_participate":  _start_participate_from_button,
        "menu_tickets":      show_my_tickets,
        "menu_history":      show_history,
        "menu_deposit":      _start_deposit_from_button,
        "menu_transactions": show_transactions,
        "menu_invite":       show_invite,
        # Admin menu
        "admin_newround":    cmd_newround,
        "admin_closeround":  cmd_closeround,
        "admin_roundinfo":   cmd_roundinfo,
        "admin_deposits":    cmd_deposits,
        "admin_members":     cmd_members,
        "admin_draw":        _draw_notice,
        # Generic
        "cancel":            _cancel_cb,
    }

    handler = routing.get(data)
    if handler:
        await handler(update, ctx)
    elif data.startswith("back_"):
        await _show_main(update, ctx)


async def _start_deposit_from_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Use the /deposit command to submit a deposit request."
    )


async def _start_participate_from_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Use the /participate command to join the current round."
    )


async def _draw_notice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Use the /draw command to run the weighted draw."
    )


async def _cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text(
        "Cancelled.", reply_markup=main_menu()
    )


async def _show_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user
    record = await db.get_user(conn, user.id)
    keyboard = admin_menu() if (record and record["is_trustee"]) else main_menu()
    await update.callback_query.message.reply_text(
        "Main menu:", reply_markup=keyboard
    )


# ──────────────────────────────────────────────
# Error handler
# ──────────────────────────────────────────────

async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception:", exc_info=ctx.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong. Please try again."
            )
        except Exception:
            pass


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

async def post_init(app: Application):
    app.bot_data["db"] = await db.get_db()
    logger.info("Database initialised.")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Conversations (must be registered before plain CommandHandlers)
    app.add_handler(build_deposit_conversation())
    app.add_handler(build_participate_conversation())
    app.add_handler(build_draw_conversation())

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("balance", show_balance))
    app.add_handler(CommandHandler("round", show_round))
    app.add_handler(CommandHandler("tickets", show_my_tickets))
    app.add_handler(CommandHandler("history", show_history))
    app.add_handler(CommandHandler("invite", show_invite))
    app.add_handler(CommandHandler("transactions", show_transactions))
    # Admin commands
    app.add_handler(CommandHandler("newround", cmd_newround))
    app.add_handler(CommandHandler("closeround", cmd_closeround))
    app.add_handler(CommandHandler("roundinfo", cmd_roundinfo))
    app.add_handler(CommandHandler("deposits", cmd_deposits))
    app.add_handler(CommandHandler("members", cmd_members))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(callback_router))

    # Errors
    app.add_error_handler(error_handler)

    logger.info("Bot starting …")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
