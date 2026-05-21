"""
Lottery handlers for regular members:
  /participate, /mytickets, /round, /history, /invite
"""

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CommandHandler, filters,
)

import database as db
from config import CURRENCY
from keyboards import main_menu

AWAITING_STAKE = 10


async def show_round(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user
    record = await db.get_user(conn, user.id)
    if not record:
        await _reply(update, "Please /start first.")
        return

    round_ = await db.get_open_round(conn)
    if not round_:
        await _reply(
            update,
            "🔴 No active lottery round right now.\n"
            "The trustee will open one soon — stay tuned!",
            keyboard=main_menu(),
        )
        return

    parts = await db.round_participations(conn, round_["id"])
    pool = round_["pool"]

    lines = [
        f"🎰 *Round #{round_['id']}* — Status: `open`\n",
        f"💵 Total Pool: *{pool:.2f} {CURRENCY}*",
        f"👥 Participants: *{len(parts)}*\n",
    ]

    if parts:
        lines.append("*Participants & Chances:*")
        for p in parts:
            pct = (p["amount"] / pool * 100) if pool else 0
            name = p["full_name"]
            lines.append(f"  • {name}: {p['amount']:.2f} ({pct:.1f}%)")

    own = await db.get_participation(conn, round_["id"], user.id)
    if own:
        pct = (own["amount"] / pool * 100) if pool else 0
        lines.append(
            f"\n🎟 *Your stake:* {own['amount']:.2f} {CURRENCY} = *{pct:.1f}%* chance"
        )
    else:
        lines.append("\nYou haven't joined this round yet. Use ➕ Participate!")

    await _reply(update, "\n".join(lines), keyboard=main_menu())


async def start_participate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user
    record = await db.get_user(conn, user.id)
    if not record:
        await _reply(update, "Please /start first.")
        return ConversationHandler.END

    round_ = await db.get_open_round(conn)
    if not round_:
        await _reply(
            update,
            "🔴 No active round. Wait for the trustee to open one.",
            keyboard=main_menu(),
        )
        return ConversationHandler.END

    balance = record["credit"]
    await _reply(
        update,
        f"🎟 *Join Round #{round_['id']}*\n\n"
        f"Your balance: *{balance:.2f} {CURRENCY}*\n\n"
        "How much do you want to stake? (full amount goes into the pool)\n"
        "_Type /cancel to abort._",
    )
    ctx.user_data["participate_round"] = round_["id"]
    return AWAITING_STAKE


async def receive_stake(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user
    record = await db.get_user(conn, user.id)

    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a valid positive number.")
        return AWAITING_STAKE

    if record["credit"] < amount:
        await update.message.reply_text(
            f"❌ Insufficient balance. You have *{record['credit']:.2f} {CURRENCY}*.\n"
            "Use ➕ Deposit to top up.",
            parse_mode="Markdown",
        )
        return AWAITING_STAKE

    round_id = ctx.user_data.get("participate_round")
    round_ = await db.get_round(conn, round_id)
    if not round_ or round_["status"] != "open":
        await update.message.reply_text(
            "Round is no longer open.", reply_markup=main_menu()
        )
        return ConversationHandler.END

    # Deduct credit, record participation & transaction
    await db.update_credit(conn, user.id, -amount)
    await db.upsert_participation(conn, round_id, user.id, amount)
    await db.add_transaction(
        conn, user.id, "participate", amount,
        note=f"Round #{round_id} stake"
    )

    # Recalculate new pool & chance
    updated_round = await db.get_round(conn, round_id)
    pool = updated_round["pool"]
    own = await db.get_participation(conn, round_id, user.id)
    pct = (own["amount"] / pool * 100) if pool else 0

    await update.message.reply_text(
        f"✅ Staked *{amount:.2f} {CURRENCY}* in Round #{round_id}!\n\n"
        f"Your total stake: *{own['amount']:.2f} {CURRENCY}*\n"
        f"Your chance: *{pct:.1f}%*\n"
        f"Total pool: *{pool:.2f} {CURRENCY}*",
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


async def cancel_participate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Participation cancelled.", reply_markup=main_menu())
    return ConversationHandler.END


async def show_my_tickets(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user
    record = await db.get_user(conn, user.id)
    if not record:
        await _reply(update, "Please /start first.")
        return

    # Current open round
    round_ = await db.get_open_round(conn)
    lines = ["🎟 *Your Tickets*\n"]

    if round_:
        own = await db.get_participation(conn, round_["id"], user.id)
        if own:
            pct = (own["amount"] / round_["pool"] * 100) if round_["pool"] else 0
            lines.append(
                f"*Current Round #{round_['id']}* (open)\n"
                f"  Stake: {own['amount']:.2f} {CURRENCY}\n"
                f"  Pool: {round_['pool']:.2f} {CURRENCY}\n"
                f"  Your chance: *{pct:.1f}%*\n"
            )
        else:
            lines.append("_You haven't joined the current round._\n")

    # Past rounds
    past = await db.user_participations(conn, user.id)
    closed = [p for p in past if p["status"] in ("closed", "drawn")]
    if closed:
        lines.append("*Past Participations:*")
        for p in closed:
            pool = p["pool"] or 1
            pct = p["amount"] / pool * 100
            won = "🏆 WON" if p["winner_id"] == user.id else ""
            lines.append(
                f"  Round #{p['round_id']}  {won}\n"
                f"    Stake: {p['amount']:.2f}  Pool: {pool:.2f}  Chance: {pct:.1f}%"
            )

    if len(lines) == 1:
        lines.append("No tickets yet. Join a round to get started!")

    await _reply(update, "\n".join(lines), keyboard=main_menu())


async def show_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    rounds = await db.recent_rounds(conn)

    if not rounds:
        await _reply(update, "No rounds yet.", keyboard=main_menu())
        return

    lines = ["🏆 *Round History*\n"]
    for r in rounds:
        status_icon = {"open": "🟢", "closed": "🟡", "drawn": "🎉"}.get(r["status"], "•")
        winner = ""
        if r["winner_id"]:
            wuser = await db.get_user(conn, r["winner_id"])
            winner = f"\n    Winner: *{wuser['full_name']}*" if wuser else ""
        ticket = f"\n    Ticket ref: `{r['ticket_ref']}`" if r["ticket_ref"] else ""
        lines.append(
            f"{status_icon} Round #{r['id']}  Pool: {r['pool']:.2f} {CURRENCY}"
            f"{winner}{ticket}"
        )

    await _reply(update, "\n".join(lines), keyboard=main_menu())


async def show_invite(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_info = await ctx.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    await _reply(
        update,
        f"🔗 *Invite a Friend*\n\n"
        f"Share this link to invite friends to join the group lottery:\n\n"
        f"`{link}`\n\n"
        "_Anyone who joins via your link will be linked to you._",
        keyboard=main_menu(),
    )


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


def build_participate_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("participate", start_participate),
        ],
        states={
            AWAITING_STAKE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_stake)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_participate)],
        per_message=False,
    )
