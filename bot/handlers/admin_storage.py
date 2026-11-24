"""Handlers for configuring and verifying the private storage channel."""

import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_back_button,
    build_cancel_fsm_button,
    build_storage_menu_keyboard,
)
from bot.middlewares.auth_middleware import IsAdminFilter
from bot.services import AuditService, ChannelService
from bot.states.admin_states import StorageChannelStates

logger = logging.getLogger(__name__)

router = Router(name="admin_storage_router")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


@router.callback_query(F.data == "admin:storage")
async def handle_storage_menu_cb(
    callback: CallbackQuery,
    repo: Repository,
    state: FSMContext,
) -> None:
    """View storage channel configuration."""
    await state.clear()
    storage_ch = await repo.get_setting("storage_channel_id")

    if storage_ch:
        status_text = f"Configured ID: `{storage_ch}`"
    else:
        status_text = "⚠️ **Not Configured!** (Uploads will fail until configured)"

    text = (
        "💾 **Private Storage Channel Configuration**\n\n"
        "Files uploaded by admins are forwarded/copied to a private channel for permanent retention. "
        "Regular users never receive direct access to this channel.\n\n"
        f"• **Current Storage Channel:** {status_text}\n\n"
        "Select an action below:"
    )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_storage_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:storage:test")
async def handle_storage_test_cb(
    callback: CallbackQuery,
    bot: Bot,
    repo: Repository,
    channel_service: ChannelService,
) -> None:
    """Test bot access and posting permissions in the storage channel."""
    storage_ch = await repo.get_setting("storage_channel_id")
    if not storage_ch:
        await callback.answer("Storage channel is not configured yet!", show_alert=True)
        return

    try:
        channel_id = int(storage_ch)
    except ValueError:
        await callback.answer("Invalid storage channel ID configured.", show_alert=True)
        return

    await callback.answer("🔍 Checking storage channel permissions...")
    success, msg, _ = await channel_service.verify_storage_channel(bot, channel_id)

    if callback.message:
        await callback.message.answer(
            f"**Storage Channel Test Result:**\n\n{msg}",
            reply_markup=build_back_button("admin:storage"),
        )


@router.callback_query(F.data == "admin:storage:change")
async def handle_storage_change_start_cb(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Start changing storage channel ID."""
    await state.set_state(StorageChannelStates.waiting_for_storage_channel_id)
    text = (
        "✏️ **Change Storage Channel**\n\n"
        "Please send the new Channel ID (e.g. `-1001987654321`).\n\n"
        "**Important Prerequisites:**\n"
        "1. Create a private Telegram channel.\n"
        "2. Add this bot as an **Administrator** with **Post Messages** privilege.\n"
        "3. Send the numeric ID here (you can forward a message to @userinfobot to get channel ID)."
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_cancel_fsm_button("admin:storage"))
    await callback.answer()


@router.message(StorageChannelStates.waiting_for_storage_channel_id)
async def process_storage_channel_id_input(
    message: Message,
    bot: Bot,
    state: FSMContext,
    repo: Repository,
    channel_service: ChannelService,
    audit_service: AuditService,
) -> None:
    """Validate and update storage channel ID."""
    raw = (message.text or "").strip()

    try:
        if raw.startswith("-100") or (raw.startswith("-") and raw[1:].isdigit()):
            channel_id = int(raw)
        elif raw.isdigit():
            channel_id = int(f"-100{raw}")
        else:
            await message.reply(
                "❌ Please enter a valid numeric channel ID starting with `-100`.",
                reply_markup=build_cancel_fsm_button("admin:storage"),
            )
            return
    except ValueError:
        await message.reply(
            "❌ Invalid numeric ID.",
            reply_markup=build_cancel_fsm_button("admin:storage"),
        )
        return

    # Verify bot presence and permissions in storage channel
    success, msg, detected_title = await channel_service.verify_storage_channel(
        bot, channel_id
    )

    if not success:
        await message.reply(
            f"⚠️ **Access Check Failed:**\n{msg}\n\n"
            "Please add the bot as an Administrator with 'Post Messages' permission in that channel, then try again.",
            reply_markup=build_cancel_fsm_button("admin:storage"),
        )
        return

    # Store setting
    await repo.set_setting("storage_channel_id", str(channel_id))
    admin_id = message.from_user.id
    await audit_service.log(
        admin_id=admin_id,
        action="update_storage_channel",
        target=str(channel_id),
        details=f"title={detected_title}",
    )
    await state.clear()

    text = (
        "✅ **Storage Channel Configured Successfully!**\n\n"
        f"• **Title:** `{detected_title or 'Private Channel'}`\n"
        f"• **Channel ID:** `{channel_id}`\n\n"
        "Files uploaded by admins will now be archived to this channel."
    )
    await message.answer(text, reply_markup=build_back_button("admin:storage"))

