"""Registration and main-menu handlers."""

import base64
import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import CURRENCY, PLATFORM_ADMIN_IDS
from group_context import join_group_by_slug, parse_invite_slug
from keyboards import main_menu, admin_menu

logger = logging.getLogger(__name__)


async def _fetch_and_store_photo(bot, user_id: int, conn) -> None:
    """Fetch Telegram profile photo via Bot API and persist as base64 data URL."""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos.photos:
            return
        photo_size  = photos.photos[0][0]          # smallest size (~160×160)
        file_obj    = await bot.get_file(photo_size.file_id)
        image_bytes = bytes(await file_obj.download_as_bytearray())
        b64         = base64.b64encode(image_bytes).decode()
        data_url    = f"data:image/jpeg;base64,{b64}"
        await conn.execute(
            "UPDATE users SET photo_url=? WHERE telegram_id=?", (data_url, user_id)
        )
        await conn.commit()
        logger.debug("Stored profile photo for %s (%d bytes)", user_id, len(image_bytes))
    except Exception as exc:
        logger.debug("Could not fetch profile photo for %s: %s", user_id, exc)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = ctx.bot_data["db"]

    invited_by: int | None = None
    group_id = None
    group_name = None
    slug = None
    if ctx.args:
        arg = ctx.args[0]
        if arg.startswith("ref_"):
            try:
                invited_by = int(arg[4:])
            except ValueError:
                pass
        slug = parse_invite_slug(arg) if arg.startswith(("g_", "join_")) else None
        if slug:
            g = await db.get_group_by_slug(conn, slug)
            if g and g["status"] == "active":
                group_id = g["id"]
                group_name = g["name"]

    is_platform = 1 if user.id in PLATFORM_ADMIN_IDS else 0
    existing = await db.get_user(conn, user.id)

    if not existing:
        await db.create_user(
            conn,
            telegram_id=user.id,
            username=user.username,
            full_name=user.full_name,
            invited_by=invited_by,
            is_trustee=0,
            group_id=group_id,
            is_platform_admin=is_platform,
        )
        if slug:
            await join_group_by_slug(conn, user.id, slug)
        if group_name:
            welcome = (
                f"👋 Welcome, *{user.first_name}*!\n\n"
                f"You've joined the *{group_name}* group lottery.\n"
                "Open the app to complete setup and play! 🎉"
            )
        else:
            welcome = (
                f"👋 Welcome, *{user.first_name}*!\n\n"
                "Ask your trustee for a group invite link to join.\n"
                "Open the Mini App when you have one."
            )
    else:
        welcome = f"👋 Welcome back, *{user.first_name}*!"
        if slug:
            err, joined = await join_group_by_slug(conn, user.id, slug)
            if not err and joined:
                welcome = f"👋 Welcome! You've joined *{joined['name']}*."
            elif err:
                welcome += f"\n\n⚠️ {err}"

    record = await db.get_user(conn, user.id)
    credit = record["credit"] if record else 0.0

    # Fetch and store profile photo (no-op if already stored or user has no photo)
    if not record or not record.get("photo_url"):
        await _fetch_and_store_photo(ctx.bot, user.id, conn)

    msg = (
        f"{welcome}\n\n"
        f"💰 *Balance:* {credit:.2f} {CURRENCY}\n\n"
        "Use the menu below to get started."
    )

    trustee_group = await db.get_group_for_trustee(conn, user.id)
    keyboard = admin_menu() if trustee_group else main_menu()
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

    trustee_group = await db.get_group_for_trustee(conn, user.id)
    keyboard = admin_menu() if trustee_group else main_menu()
    await update.message.reply_text(
        "Choose an option:", reply_markup=keyboard
    )
