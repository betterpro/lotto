"""
Trustee-only admin handlers.
Draw uses a weighted random selection based on each participant's stake.
"""

import random
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CommandHandler, filters,
)

import database as db
from config import CURRENCY, TRUSTEE_ID
from keyboards import admin_menu, main_menu

AWAITING_TICKET_REF = 20
AWAITING_WINNER_CONFIRM = 21


def _is_trustee(record) -> bool:
    return record is not None and record["is_trustee"]


async def _auth(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = ctx.bot_data["db"]
    user = update.effective_user
    record = await db.get_user(conn, user.id)
    if not _is_trustee(record):
        await _reply(update, "⛔ Trustee only.")
        return None
    return record


# ──────────────────────────────────────────────
# Open new round
# ──────────────────────────────────────────────

async def cmd_newround(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _auth(update, ctx):
        return

    conn = ctx.bot_data["db"]
    existing = await db.get_open_round(conn)
    if existing:
        await _reply(
            update,
            f"⚠️ Round #{existing['id']} is already open. Close it first.",
            keyboard=admin_menu(),
        )
        return

    round_id = await db.create_round(conn)
    await _reply(
        update,
        f"✅ *Round #{round_id} opened!*\n\nMembers can now participate.",
        keyboard=admin_menu(),
    )


# ──────────────────────────────────────────────
# Close round (no more entries)
# ──────────────────────────────────────────────

async def cmd_closeround(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _auth(update, ctx):
        return

    conn = ctx.bot_data["db"]
    round_ = await db.get_open_round(conn)
    if not round_:
        await _reply(update, "No open round to close.", keyboard=admin_menu())
        return

    await db.close_round(conn, round_["id"])
    parts = await db.round_participations(conn, round_["id"])
    await _reply(
        update,
        f"🔒 *Round #{round_['id']} closed.*\n\n"
        f"Pool: *{round_['pool']:.2f} {CURRENCY}*\n"
        f"Participants: {len(parts)}\n\n"
        "Use 🎲 Draw Winner when you're ready.",
        keyboard=admin_menu(),
    )


# ──────────────────────────────────────────────
# Draw winner
# ──────────────────────────────────────────────

async def cmd_draw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _auth(update, ctx):
        return

    conn = ctx.bot_data["db"]

    # Find the most recent closed round
    async with conn.execute(
        "SELECT * FROM rounds WHERE status='closed' ORDER BY id DESC LIMIT 1"
    ) as cur:
        round_ = await cur.fetchone()

    if not round_:
        open_round = await db.get_open_round(conn)
        if open_round:
            await _reply(
                update,
                "Please close the current round before drawing.",
                keyboard=admin_menu(),
            )
        else:
            await _reply(update, "No closed round to draw.", keyboard=admin_menu())
        return

    parts = await db.round_participations(conn, round_["id"])
    if not parts:
        await _reply(
            update,
            f"⚠️ Round #{round_['id']} has no participants.",
            keyboard=admin_menu(),
        )
        return

    # Weighted random draw
    population = [p["user_id"] for p in parts]
    weights = [p["amount"] for p in parts]
    winner_id = random.choices(population, weights=weights, k=1)[0]
    winner = await db.get_user(conn, winner_id)

    pool = round_["pool"]
    winner_pct = next(
        (p["amount"] / pool * 100 for p in parts if p["user_id"] == winner_id), 0
    )

    # Store for confirmation step
    ctx.user_data["pending_draw"] = {
        "round_id": round_["id"],
        "winner_id": winner_id,
        "pool": pool,
        "winner_pct": winner_pct,
        "winner_name": winner["full_name"] if winner else "Unknown",
    }

    await _reply(
        update,
        f"🎲 *Draw Result — Round #{round_['id']}*\n\n"
        f"Pool: *{pool:.2f} {CURRENCY}*\n"
        f"Winner: *{winner['full_name']}* ({winner_pct:.1f}% chance)\n\n"
        f"Enter the external ticket/reference number (or send `-` to skip), "
        f"then type *CONFIRM* to finalise:",
    )
    return AWAITING_TICKET_REF


async def receive_ticket_ref(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ctx.user_data["pending_draw"]["ticket_ref"] = None if text == "-" else text
    draw = ctx.user_data["pending_draw"]
    await update.message.reply_text(
        f"📋 Ready to finalise:\n\n"
        f"Winner: *{draw['winner_name']}*\n"
        f"Prize: *{draw['pool']:.2f} {CURRENCY}*\n"
        f"Ticket ref: `{draw.get('ticket_ref') or 'N/A'}`\n\n"
        f"Type *CONFIRM* to credit winner and notify all participants, or /cancel to abort.",
        parse_mode="Markdown",
    )
    return AWAITING_WINNER_CONFIRM


async def confirm_draw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().upper() != "CONFIRM":
        await update.message.reply_text("Type CONFIRM to proceed or /cancel to abort.")
        return AWAITING_WINNER_CONFIRM

    conn = ctx.bot_data["db"]
    draw = ctx.user_data.pop("pending_draw", None)
    if not draw:
        await update.message.reply_text("No pending draw.", reply_markup=admin_menu())
        return ConversationHandler.END

    round_id = draw["round_id"]
    winner_id = draw["winner_id"]
    pool = draw["pool"]

    # Credit winner
    await db.update_credit(conn, winner_id, pool)
    await db.add_transaction(
        conn, winner_id, "win", pool, note=f"Round #{round_id} prize"
    )
    await db.set_round_winner(conn, round_id, winner_id, draw.get("ticket_ref"))

    # Notify all participants
    parts = await db.round_participations(conn, round_id)
    winner_name = draw["winner_name"]
    for p in parts:
        pct = (p["amount"] / pool * 100) if pool else 0
        try:
            if p["user_id"] == winner_id:
                msg = (
                    f"🏆 *Congratulations!* You won Round #{round_id}!\n\n"
                    f"Prize *{pool:.2f} {CURRENCY}* added to your balance.\n"
                    f"Your stake was {p['amount']:.2f} ({pct:.1f}% chance)."
                )
            else:
                msg = (
                    f"🎰 *Round #{round_id} Result*\n\n"
                    f"Winner: *{winner_name}*\n"
                    f"Pool: {pool:.2f} {CURRENCY}\n"
                    f"Your stake: {p['amount']:.2f} ({pct:.1f}% chance)\n\n"
                    "Better luck next time! 🍀"
                )
            await ctx.bot.send_message(
                chat_id=p["user_id"],
                text=msg,
                parse_mode="Markdown",
                reply_markup=main_menu(),
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ *Round #{round_id} finalised!*\n\n"
        f"Winner: *{winner_name}*\n"
        f"Prize: *{pool:.2f} {CURRENCY}* credited.",
        parse_mode="Markdown",
        reply_markup=admin_menu(),
    )
    return ConversationHandler.END


async def cancel_draw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("pending_draw", None)
    await update.message.reply_text("Draw cancelled.", reply_markup=admin_menu())
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Round info
# ──────────────────────────────────────────────

async def cmd_roundinfo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _auth(update, ctx):
        return

    conn = ctx.bot_data["db"]
    round_ = await db.get_open_round(conn)

    if not round_:
        # Show latest closed/drawn
        async with conn.execute(
            "SELECT * FROM rounds ORDER BY id DESC LIMIT 1"
        ) as cur:
            round_ = await cur.fetchone()

    if not round_:
        await _reply(update, "No rounds yet.", keyboard=admin_menu())
        return

    parts = await db.round_participations(conn, round_["id"])
    pool = round_["pool"]

    lines = [
        f"📋 *Round #{round_['id']}* — `{round_['status']}`\n",
        f"Pool: *{pool:.2f} {CURRENCY}*",
        f"Participants: {len(parts)}\n",
    ]
    for p in parts:
        pct = (p["amount"] / pool * 100) if pool else 0
        name = p["full_name"]
        lines.append(f"  • {name}: {p['amount']:.2f} ({pct:.1f}%)")

    await _reply(update, "\n".join(lines), keyboard=admin_menu())


# ──────────────────────────────────────────────
# Pending deposits list
# ──────────────────────────────────────────────

async def cmd_deposits(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _auth(update, ctx):
        return

    conn = ctx.bot_data["db"]
    pending = await db.pending_deposits(conn)

    if not pending:
        await _reply(update, "✅ No pending deposits.", keyboard=admin_menu())
        return

    lines = [f"💵 *{len(pending)} Pending Deposit(s):*\n"]
    from keyboards import deposit_approval
    for req in pending:
        name = req["full_name"]
        uname = f"@{req['username']}" if req["username"] else "no username"
        lines.append(
            f"#{req['id']} — *{name}* ({uname})\n"
            f"  Amount: {req['amount']:.2f} {CURRENCY}  |  {req['created_at'][:10]}"
        )

    await _reply(update, "\n".join(lines), keyboard=admin_menu())

    # Resend each with approval buttons
    msg = update.callback_query.message if update.callback_query else update.message
    for req in pending:
        name = req["full_name"]
        await msg.reply_text(
            f"Deposit #{req['id']} — *{name}*: {req['amount']:.2f} {CURRENCY}",
            parse_mode="Markdown",
            reply_markup=deposit_approval(req["id"]),
        )


# ──────────────────────────────────────────────
# Members list
# ──────────────────────────────────────────────

async def cmd_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await _auth(update, ctx):
        return

    conn = ctx.bot_data["db"]
    users = await db.all_users(conn)

    lines = [f"👥 *Members ({len(users)})*\n"]
    for u in users:
        trustee_tag = " 👑" if u["is_trustee"] else ""
        uname = f"@{u['username']}" if u["username"] else "no username"
        lines.append(
            f"• *{u['full_name']}*{trustee_tag} ({uname})\n"
            f"  Balance: {u['credit']:.2f} {CURRENCY}  |  Since: {u['created_at'][:10]}"
        )

    await _reply(update, "\n".join(lines), keyboard=admin_menu())


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


def build_draw_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("draw", cmd_draw)],
        states={
            AWAITING_TICKET_REF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ticket_ref)
            ],
            AWAITING_WINNER_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_draw)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_draw)],
        per_message=False,
    )
