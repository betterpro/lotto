"""
Credit handlers: deposit requests, balance, transaction history.
Users request a deposit → trustee approves/rejects via inline buttons.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CommandHandler

import database as db
from config import CURRENCY, TRUSTEE_ID
from keyboards import main_menu, back_button

AWAITING_DEPOSIT_AMOUNT = 1


async def show_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = ctx.bot_data["db"]
    record = await db.get_user(conn, user.id)

    if not record:
        await _reply(update, "Please /start first.")
        return

    credit = record["credit"]
    text = (
        f"💰 *Your Balance*\n\n"
        f"Available credit: *{credit:.2f} {CURRENCY}*\n\n"
        "Use ➕ Deposit to add more credit."
    )
    await _reply(update, text, keyboard=main_menu())


async def start_deposit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    record = await db.get_user(conn, update.effective_user.id)
    if not record:
        await _reply(update, "Please /start first.")
        return ConversationHandler.END

    await _reply(
        update,
        f"💵 *Deposit Request*\n\nEnter the amount you want to deposit (in {CURRENCY}):\n"
        "_Type /cancel to abort._",
    )
    return AWAITING_DEPOSIT_AMOUNT


async def receive_deposit_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user

    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid positive number.")
        return AWAITING_DEPOSIT_AMOUNT

    req_id = await db.create_deposit_request(conn, user.id, amount)

    user_record = await db.get_user(conn, user.id)
    name = user_record["full_name"]
    uname = f"@{user_record['username']}" if user_record["username"] else "no username"

    # Notify trustee
    from keyboards import deposit_approval
    trustee_msg = (
        f"💵 *Deposit Request #{req_id}*\n\n"
        f"From: *{name}* ({uname})\n"
        f"Amount: *{amount:.2f} {CURRENCY}*\n\n"
        "Approve or reject this request:"
    )
    try:
        await ctx.bot.send_message(
            chat_id=TRUSTEE_ID,
            text=trustee_msg,
            parse_mode="Markdown",
            reply_markup=deposit_approval(req_id),
        )
    except Exception:
        pass  # trustee may not have started the bot yet

    await update.message.reply_text(
        f"✅ Deposit request of *{amount:.2f} {CURRENCY}* sent to the trustee.\n"
        "You'll be notified once it's approved.",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


async def cancel_deposit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Deposit cancelled.", reply_markup=main_menu()
    )
    return ConversationHandler.END


# Callback: trustee approves/rejects
async def handle_deposit_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    conn = ctx.bot_data["db"]
    trustee = await db.get_user(conn, query.from_user.id)
    if not trustee or not trustee["is_trustee"]:
        await query.answer("Not authorised.", show_alert=True)
        return

    parts = query.data.split("_")   # dep_approve_<id>  or  dep_reject_<id>
    action = parts[1]
    req_id = int(parts[2])

    req = await db.get_deposit_request(conn, req_id)
    if not req:
        await query.edit_message_text("Request not found.")
        return
    if req["status"] != "pending":
        await query.edit_message_text(
            f"Request #{req_id} already {req['status']}."
        )
        return

    if action == "approve":
        await db.update_credit(conn, req["user_id"], req["amount"])
        await db.add_transaction(
            conn, req["user_id"], "deposit", req["amount"],
            note=f"Deposit request #{req_id} approved"
        )
        await db.resolve_deposit(conn, req_id, "approved")

        # Notify user
        try:
            await ctx.bot.send_message(
                chat_id=req["user_id"],
                text=(
                    f"✅ Your deposit of *{req['amount']:.2f} {CURRENCY}* has been approved!\n"
                    "Your credit has been updated."
                ),
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
        except Exception:
            pass

        await query.edit_message_text(
            f"✅ Deposit #{req_id} approved — *{req['amount']:.2f} {CURRENCY}* added to user.",
            parse_mode="Markdown",
        )

    else:  # reject
        await db.resolve_deposit(conn, req_id, "rejected")
        try:
            await ctx.bot.send_message(
                chat_id=req["user_id"],
                text=(
                    f"❌ Your deposit request of *{req['amount']:.2f} {CURRENCY}* "
                    "was rejected by the trustee.\nContact them for details."
                ),
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
        except Exception:
            pass

        await query.edit_message_text(
            f"❌ Deposit #{req_id} rejected.", parse_mode="Markdown"
        )


async def show_transactions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = ctx.bot_data["db"]
    record = await db.get_user(conn, user.id)
    if not record:
        await _reply(update, "Please /start first.")
        return

    txs = await db.user_transactions(conn, user.id)
    if not txs:
        await _reply(update, "No transactions yet.", keyboard=main_menu())
        return

    lines = ["📋 *Recent Transactions*\n"]
    icons = {
        "deposit": "➕", "withdraw": "➖",
        "participate": "🎟", "win": "🏆", "refund": "↩️",
    }
    for tx in txs:
        icon = icons.get(tx["type"], "•")
        sign = "+" if tx["type"] in ("deposit", "win", "refund") else "-"
        lines.append(
            f"{icon} {sign}{tx['amount']:.2f} {CURRENCY}  "
            f"_{tx['type']}_ — {tx['created_at'][:10]}"
        )

    await _reply(update, "\n".join(lines), keyboard=main_menu())


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def _reply(update: Update, text: str, keyboard=None):
    kwargs = {"text": text, "parse_mode": "Markdown"}
    if keyboard:
        kwargs["reply_markup"] = keyboard

    if update.callback_query:
        await update.callback_query.message.reply_text(**kwargs)
    else:
        await update.message.reply_text(**kwargs)


def build_deposit_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("deposit", start_deposit),
        ],
        states={
            AWAITING_DEPOSIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deposit_amount)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_deposit)],
        per_message=False,
    )
