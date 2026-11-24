"""Handlers for direct media uploads by authorized admins."""

import logging
from aiogram import Bot, F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database.repository import Repository
from bot.middlewares.auth_middleware import IsAdminFilter
from bot.services import (
    AuditService,
    FileService,
    format_file_size,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_upload_router")
# Protect all handlers in this router with IsAdminFilter
router.message.filter(IsAdminFilter())


@router.message(
    F.document | F.video | F.audio | F.photo | F.animation | F.voice | F.video_note
)
async def handle_admin_file_upload(
    message: Message,
    bot: Bot,
    repo: Repository,
    file_service: FileService,
    audit_service: AuditService,
) -> None:
    """Handles any media sent to the bot by an authorized admin."""
    admin_id = message.from_user.id

    # 1. Check storage channel configuration
    storage_channel_str = await repo.get_setting("storage_channel_id")
    if not storage_channel_str:
        await message.reply(
            "⚠️ **Storage Channel Not Configured!**\n\n"
            "Please configure the private storage channel before uploading files.\n"
            "Open `/panel` -> **💾 Storage Channel** to configure it."
        )
        return

    try:
        storage_channel_id = int(storage_channel_str)
    except ValueError:
        await message.reply("❌ Configured storage channel ID is invalid. Please reconfigure via `/panel`.")
        return

    # 2. Get default expiry and limits
    default_expiry_str = await repo.get_setting("default_expiry_hours", "0")
    default_limit_str = await repo.get_setting("default_delivery_limit", "0")

    try:
        default_expiry = int(default_expiry_str)
    except ValueError:
        default_expiry = 0

    try:
        default_limit = int(default_limit_str)
    except ValueError:
        default_limit = 0

    expiry_hours = default_expiry if default_expiry > 0 else None
    delivery_limit = default_limit if default_limit > 0 else None

    # 3. Store file and generate link
    status_msg = await message.reply("⏳ Storing file in secure private storage...")

    try:
        file_record, token = await file_service.store_file_from_message(
            bot=bot,
            message=message,
            admin_id=admin_id,
            storage_channel_id=storage_channel_id,
            expiry_hours=expiry_hours,
            delivery_limit=delivery_limit,
        )

        bot_info = await bot.get_me()
        deep_link = f"https://t.me/{bot_info.username}?start={token}"

        response_text = (
            "✅ **File Stored Successfully!**\n\n"
            f"📁 **Name:** `{file_record.file_name}`\n"
            f"📊 **Size:** `{format_file_size(file_record.file_size)}`\n"
            f"🎬 **Type:** `{file_record.media_type}`\n"
            f"🔑 **Token:** `{token}`\n"
        )

        if file_record.expires_at:
            response_text += f"⏱ **Expires:** `{file_record.expires_at.strftime('%Y-%m-%d %H:%M UTC')}`\n"
        if file_record.delivery_limit:
            response_text += f"🛑 **Per-User Limit:** `{file_record.delivery_limit}` downloads\n"

        autodel_val = await repo.get_setting("auto_delete_minutes", "0")
        if autodel_val != "0":
            response_text += f"🗑 **Auto-Delete:** `{autodel_val}` minutes\n"

        response_text += (
            f"\n🔗 **Shareable Deep Link:**\n"
            f"`{deep_link}`\n\n"
            "_Users who open this link will be verified for required channels before receiving the file._"
        )

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📁 View File Details",
                        callback_data=f"admin:file:view:{file_record.id}",
                    ),
                    InlineKeyboardButton(
                        text="🗑 Set Auto-Delete",
                        callback_data=f"admin:file:autodel:{file_record.id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🟡 Disable Link",
                        callback_data=f"admin:file:toggle:{file_record.id}",
                    ),
                    InlineKeyboardButton(
                        text="🔙 Main Panel", callback_data="admin:menu"
                    ),
                ],
            ]
        )

        await status_msg.edit_text(response_text, reply_markup=kb)

        await audit_service.log(
            admin_id=admin_id,
            action="upload_file",
            target=token,
            details=f"file_name={file_record.file_name}, size={file_record.file_size}",
        )

    except Exception as e:
        logger.error("Failed to store uploaded file: %s", e)
        await status_msg.edit_text(f"❌ Failed to store file: {str(e)}")

