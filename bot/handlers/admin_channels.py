"""Handlers for managing required subscription channels."""

import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import RequiredChannel
from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_back_button,
    build_cancel_fsm_button,
    build_channel_detail_keyboard,
    build_channels_list_keyboard,
    build_confirmation_keyboard,
)
from bot.middlewares.auth_middleware import IsAdminFilter
from bot.services import AuditService, ChannelService
from bot.states.admin_states import AddChannelStates, EditChannelStates

logger = logging.getLogger(__name__)

router = Router(name="admin_channels_router")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


# ==================== COMMANDS ====================


@router.message(Command("channels"))
async def handle_channels_command(message: Message, repo: Repository) -> None:
    """List required channels command."""
    channels = await repo.list_required_channels()
    text = (
        "📢 **Configured Required Channels**\n\n"
        f"Total channels configured: `{len(channels)}`\n"
        "Click on a channel below to view details, test permissions, or toggle status:"
    )
    await message.answer(text, reply_markup=build_channels_list_keyboard(channels))


@router.message(Command("addchannel"))
async def handle_addchannel_command(message: Message, state: FSMContext) -> None:
    """Start add channel wizard."""
    await state.set_state(AddChannelStates.waiting_for_channel_id)
    text = (
        "➕ **Add Required Subscription Channel**\n\n"
        "Please send the Telegram Channel ID (e.g., `-1001234567890`) or channel username (e.g., `@mychannel`).\n\n"
        "💡 *Tip: Make sure you have added the bot to the channel as an Administrator first!*"
    )
    await message.answer(text, reply_markup=build_cancel_fsm_button("admin:channels:list"))


@router.message(Command("removechannel"))
async def handle_removechannel_command(message: Message, repo: Repository) -> None:
    """Show channels for removal."""
    channels = await repo.list_required_channels()
    if not channels:
        await message.answer("ℹ️ No required channels are configured.")
        return
    text = "🗑 **Remove Required Channel**\n\nSelect a channel below to delete it:"
    await message.answer(text, reply_markup=build_channels_list_keyboard(channels))


# ==================== CALLBACKS ====================


@router.callback_query(F.data == "admin:channels:list")
async def handle_channels_list_cb(callback: CallbackQuery, repo: Repository, state: FSMContext) -> None:
    """Channels menu callback."""
    await state.clear()
    channels = await repo.list_required_channels()
    text = (
        "📢 **Configured Required Channels**\n\n"
        f"Total channels: `{len(channels)}`\n"
        "Select a channel to inspect or tap **Add Required Channel** below:"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_channels_list_keyboard(channels))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:chan:view:"))
async def handle_channel_view_cb(callback: CallbackQuery, repo: Repository) -> None:
    """View details of a specific channel."""
    channel_id = int(callback.data.split(":", 3)[3])
    channel = await repo.get_required_channel(channel_id)

    if not channel:
        await callback.answer("❌ Channel not found.", show_alert=True)
        return

    status_str = "🟢 Enabled (Active Check)" if channel.is_enabled else "🔴 Disabled (Not Enforced)"
    created_str = channel.created_at.strftime("%Y-%m-%d %H:%M") if channel.created_at else "Unknown"

    text = (
        f"📢 **Channel Details**\n\n"
        f"• **Display Name:** `{channel.display_name}`\n"
        f"• **Channel ID:** `{channel.channel_id}`\n"
        f"• **Join URL:** `{channel.join_url}`\n"
        f"• **Status:** {status_str}\n"
        f"• **Added Date:** `{created_str}`\n"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_channel_detail_keyboard(channel))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:chan:toggle:"))
async def handle_channel_toggle_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Toggle channel enabled / disabled status."""
    channel_id = int(callback.data.split(":", 3)[3])
    channel = await repo.get_required_channel(channel_id)

    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    new_status = not channel.is_enabled
    await repo.update_channel_status(channel_id, new_status)
    channel.is_enabled = new_status

    await audit_service.log(
        admin_id=callback.from_user.id,
        action="toggle_channel",
        target=str(channel_id),
        details=f"enabled={new_status}",
    )

    await callback.answer(f"Channel {'enabled' if new_status else 'disabled'}.")
    # Refresh view
    status_str = "🟢 Enabled" if channel.is_enabled else "🔴 Disabled"
    text = (
        f"📢 **Channel Details**\n\n"
        f"• **Display Name:** `{channel.display_name}`\n"
        f"• **Channel ID:** `{channel.channel_id}`\n"
        f"• **Join URL:** `{channel.join_url}`\n"
        f"• **Status:** {status_str}\n"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_channel_detail_keyboard(channel))


@router.callback_query(F.data.startswith("admin:chan:test:"))
async def handle_channel_test_cb(
    callback: CallbackQuery, bot: Bot, channel_service: ChannelService
) -> None:
    """Test if bot has admin permissions to inspect members in channel."""
    channel_id = int(callback.data.split(":", 3)[3])
    await callback.answer("🔍 Checking bot permissions in channel...")

    success, msg, _ = await channel_service.verify_channel_access(bot, channel_id)
    if callback.message:
        await callback.message.answer(
            f"**Channel Permissions Test Result:**\n\n{msg}",
            reply_markup=build_back_button(f"admin:chan:view:{channel_id}"),
        )


@router.callback_query(F.data.startswith("admin:chan:del_conf:"))
async def handle_channel_delete_confirm_cb(callback: CallbackQuery, repo: Repository) -> None:
    """Show confirmation before deleting channel."""
    channel_id = int(callback.data.split(":", 3)[3])
    channel = await repo.get_required_channel(channel_id)

    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    text = (
        f"⚠️ **Are you sure you want to remove this channel?**\n\n"
        f"• **Channel:** `{channel.display_name}` (`{channel.channel_id}`)\n\n"
        "Users will no longer be required to join this channel to access files."
    )
    confirm_data = f"admin:chan:delete:{channel_id}"
    cancel_data = f"admin:chan:view:{channel_id}"
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_confirmation_keyboard(confirm_data, cancel_data)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:chan:delete:"))
async def handle_channel_delete_execute_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Execute deletion of required channel."""
    channel_id = int(callback.data.split(":", 3)[3])
    channel = await repo.get_required_channel(channel_id)

    await repo.delete_required_channel(channel_id)
    await audit_service.log(
        admin_id=callback.from_user.id,
        action="delete_channel",
        target=str(channel_id),
        details=f"name={channel.display_name if channel else 'unknown'}",
    )

    await callback.answer("Channel removed successfully!", show_alert=True)
    channels = await repo.list_required_channels()
    text = (
        "📢 **Configured Required Channels**\n\n"
        "Channel was removed.\n"
        f"Total remaining channels: `{len(channels)}`"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_channels_list_keyboard(channels))


# ==================== ADD CHANNEL WIZARD FSM ====================


@router.callback_query(F.data == "admin:chan:add")
async def handle_channel_add_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Start add channel wizard via callback button."""
    await state.set_state(AddChannelStates.waiting_for_channel_id)
    text = (
        "➕ **Add Required Subscription Channel (Step 1/3)**\n\n"
        "Please send the Telegram Channel ID (e.g. `-1001234567890`) or `@channel_username`.\n\n"
        "Ensure the bot is already added to the channel as an Administrator."
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_cancel_fsm_button("admin:channels:list"))
    await callback.answer()


@router.message(AddChannelStates.waiting_for_channel_id)
async def process_channel_id_input(
    message: Message, bot: Bot, state: FSMContext, channel_service: ChannelService
) -> None:
    """Process channel ID, username, or t.me link input."""
    raw_input = (message.text or "").strip()

    # Extract clean username if a full link was passed (e.g. https://t.me/Steal_Zone)
    clean_username = None
    if "t.me/" in raw_input:
        part = raw_input.split("t.me/")[-1].strip().split("/")[0].split("?")[0]
        if part and not part.startswith("+") and not part.startswith("joinchat"):
            clean_username = f"@{part}"

    try:
        if raw_input.startswith("-100") or (raw_input.startswith("-") and raw_input[1:].isdigit()):
            channel_id = int(raw_input)
        elif raw_input.isdigit():
            # If user forgot negative sign for supergroup/channel:
            channel_id = int(f"-100{raw_input}")
        elif clean_username:
            chat = await bot.get_chat(clean_username)
            channel_id = chat.id
        elif raw_input.startswith("@"):
            chat = await bot.get_chat(raw_input)
            channel_id = chat.id
        elif any(c.isalnum() for c in raw_input) and not raw_input.startswith("http"):
            # Username without @ (e.g. Steal_Zone)
            chat = await bot.get_chat(f"@{raw_input}")
            channel_id = chat.id
        else:
            await message.reply(
                "❌ Invalid format. Please enter a numeric channel ID (e.g. `-1001234567890`), `@username`, or link (`https://t.me/channel_name`).",
                reply_markup=build_cancel_fsm_button("admin:channels:list"),
            )
            return
    except Exception as e:
        await message.reply(
            f"❌ Could not resolve channel '{raw_input}': {e}. Ensure the bot is added to the channel as an Administrator.",
            reply_markup=build_cancel_fsm_button("admin:channels:list"),
        )
        return

    # Verify bot access in the channel
    success, msg, detected_title = await channel_service.verify_channel_access(bot, channel_id)
    if not success:
        await message.reply(
            f"⚠️ **Access Verification Warning:**\n{msg}\n\n"
            "Please grant Administrator privileges to the bot in this channel, or enter another channel ID.",
            reply_markup=build_cancel_fsm_button("admin:channels:list"),
        )
        return

    suggested = detected_title or f"Channel {channel_id}"
    suggested_url = f"https://t.me/{clean_username[1:]}" if clean_username else (
        f"https://t.me/{raw_input[1:]}" if raw_input.startswith("@") else None
    )

    await state.update_data(
        channel_id=channel_id,
        suggested_name=suggested,
        suggested_url=suggested_url,
    )
    await state.set_state(AddChannelStates.waiting_for_display_name)

    text = (
        f"✅ Channel verified: `{suggested}` (`{channel_id}`)\n\n"
        "**Step 2/3: Display Name**\n"
        f"Enter the name that will appear on buttons for users (symbols like `_` and `-` are supported), or send `/skip` to use `{suggested}`:"
    )
    await message.answer(text, reply_markup=build_cancel_fsm_button("admin:channels:list"))


@router.message(AddChannelStates.waiting_for_display_name)
async def process_channel_display_name(message: Message, state: FSMContext) -> None:
    """Process channel display name."""
    data = await state.get_data()
    user_text = (message.text or "").strip()

    if user_text == "/skip" or not user_text:
        display_name = data.get("suggested_name", f"Channel {data['channel_id']}")
    else:
        display_name = user_text

    await state.update_data(display_name=display_name)
    await state.set_state(AddChannelStates.waiting_for_join_url)

    suggested_url = data.get("suggested_url")
    skip_hint = f", or send `/skip` to use `{suggested_url}`" if suggested_url else ""

    text = (
        f"Display Name set to: `{display_name}`\n\n"
        "**Step 3/3: Join URL**\n"
        f"Please send the public link or invite link (e.g. `https://t.me/Steal_Zone` or `https://t.me/+AbCdEfGh`){skip_hint}:"
    )
    await message.answer(text, reply_markup=build_cancel_fsm_button("admin:channels:list"))


@router.message(AddChannelStates.waiting_for_join_url)
async def process_channel_join_url(
    message: Message,
    state: FSMContext,
    repo: Repository,
    audit_service: AuditService,
) -> None:
    """Process join URL and save channel."""
    raw_url = (message.text or "").strip()
    data = await state.get_data()

    if raw_url == "/skip" and data.get("suggested_url"):
        url = data["suggested_url"]
    else:
        url = raw_url

    # Clean accidental double-pasted URLs (e.g. https://...https://...)
    if "https://" in url[8:]:
        second_idx = url.find("https://", 8)
        url = url[:second_idx].strip()
    elif "http://" in url[7:]:
        second_idx = url.find("http://", 7)
        url = url[:second_idx].strip()

    # Normalize link formats (handles affiliate links, bot referrals, t.me links, external URLs)
    if url.startswith("@"):
        url = f"https://t.me/{url[1:]}"
    elif url.startswith("t.me/"):
        url = f"https://{url}"
    elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        if "/" not in url and not url.startswith("+") and not url.startswith("?"):
            url = f"https://t.me/{url}"
        else:
            url = f"https://{url}"

    if not (url.startswith("https://") or url.startswith("http://") or url.startswith("tg://")):
        await message.reply(
            "❌ Invalid URL. Please provide a valid link (e.g. `https://t.me/...` or affiliate link `https://...`).",
            reply_markup=build_cancel_fsm_button("admin:channels:list"),
        )
        return

    data = await state.get_data()
    channel_id = data["channel_id"]
    display_name = data["display_name"]
    admin_id = message.from_user.id

    new_channel = RequiredChannel(
        channel_id=channel_id,
        display_name=display_name,
        join_url=url,
        is_enabled=True,
        added_by=admin_id,
    )

    await repo.add_required_channel(new_channel)
    await audit_service.log(
        admin_id=admin_id,
        action="add_channel",
        target=str(channel_id),
        details=f"name={display_name}, url={url}",
    )

    await state.clear()

    text = (
        "🎉 **Channel Successfully Added!**\n\n"
        f"• **Name:** `{display_name}`\n"
        f"• **Channel ID:** `{channel_id}`\n"
        f"• **Join URL:** `{url}`\n"
        f"• **Status:** 🟢 Enabled\n\n"
        "Users requesting files will now be required to join this channel before receiving files."
    )
    channels = await repo.list_required_channels()
    await message.answer(text, reply_markup=build_channels_list_keyboard(channels))


# ==================== EDIT CHANNEL ====================


@router.callback_query(F.data.startswith("admin:chan:edit_name:"))
async def handle_channel_edit_name_cb(
    callback: CallbackQuery, repo: Repository, state: FSMContext
) -> None:
    """Prompt admin to enter new display name for channel."""
    channel_id = int(callback.data.split(":", 3)[3])
    channel = await repo.get_required_channel(channel_id)
    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    await state.update_data(channel_id=channel_id)
    await state.set_state(EditChannelStates.waiting_for_display_name)
    text = (
        f"✏️ **Edit Display Name for Channel `{channel.channel_id}`**\n\n"
        f"Current name: `{channel.display_name}`\n\n"
        "Please send the new display name:"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button(f"admin:chan:view:{channel_id}")
        )
    await callback.answer()


@router.message(EditChannelStates.waiting_for_display_name)
async def process_channel_edit_name_input(
    message: Message,
    state: FSMContext,
    repo: Repository,
    audit_service: AuditService,
) -> None:
    """Update channel display name."""
    new_name = (message.text or "").strip()
    if not new_name:
        await message.reply("❌ Display name cannot be empty.")
        return

    data = await state.get_data()
    channel_id = data["channel_id"]
    channel = await repo.get_required_channel(channel_id)
    if not channel:
        await message.reply("Channel not found.")
        await state.clear()
        return

    await repo.update_channel_details(channel_id, new_name, channel.join_url)
    channel.display_name = new_name
    await audit_service.log(
        admin_id=message.from_user.id,
        action="edit_channel_name",
        target=str(channel_id),
        details=f"new_name={new_name}",
    )
    await state.clear()

    status_str = "🟢 Enabled" if channel.is_enabled else "🔴 Disabled"
    text = (
        "✅ **Channel Name Updated!**\n\n"
        f"• **Display Name:** `{channel.display_name}`\n"
        f"• **Channel ID:** `{channel.channel_id}`\n"
        f"• **Join URL:** `{channel.join_url}`\n"
        f"• **Status:** {status_str}\n"
    )
    await message.answer(text, reply_markup=build_channel_detail_keyboard(channel))


@router.callback_query(F.data.startswith("admin:chan:edit_url:"))
async def handle_channel_edit_url_cb(
    callback: CallbackQuery, repo: Repository, state: FSMContext
) -> None:
    """Prompt admin to enter new join URL for channel."""
    channel_id = int(callback.data.split(":", 3)[3])
    channel = await repo.get_required_channel(channel_id)
    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    await state.update_data(channel_id=channel_id)
    await state.set_state(EditChannelStates.waiting_for_join_url)
    text = (
        f"🔗 **Edit Join URL for `{channel.display_name}`**\n\n"
        f"Current URL: `{channel.join_url}`\n\n"
        "Please send the new join URL (e.g. `https://t.me/channel`):"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button(f"admin:chan:view:{channel_id}")
        )
    await callback.answer()


@router.message(EditChannelStates.waiting_for_join_url)
async def process_channel_edit_url_input(
    message: Message,
    state: FSMContext,
    repo: Repository,
    audit_service: AuditService,
) -> None:
    """Update channel join URL."""
    raw_url = (message.text or "").strip()
    url = raw_url

    # Clean accidental double-pasted URLs (e.g. https://...https://...)
    if "https://" in url[8:]:
        second_idx = url.find("https://", 8)
        url = url[:second_idx].strip()
    elif "http://" in url[7:]:
        second_idx = url.find("http://", 7)
        url = url[:second_idx].strip()

    # Normalize link formats
    if url.startswith("@"):
        url = f"https://t.me/{url[1:]}"
    elif url.startswith("t.me/"):
        url = f"https://{url}"
    elif not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        if "/" not in url and not url.startswith("+") and not url.startswith("?"):
            url = f"https://t.me/{url}"
        else:
            url = f"https://{url}"

    if not (url.startswith("https://") or url.startswith("http://") or url.startswith("tg://")):
        await message.reply(
            "❌ Invalid URL. Please provide a valid link (e.g. `https://t.me/...` or affiliate link `https://...`)."
        )
        return

    data = await state.get_data()
    channel_id = data["channel_id"]
    channel = await repo.get_required_channel(channel_id)
    if not channel:
        await message.reply("Channel not found.")
        await state.clear()
        return

    await repo.update_channel_details(channel_id, channel.display_name, url)
    channel.join_url = url
    await audit_service.log(
        admin_id=message.from_user.id,
        action="edit_channel_url",
        target=str(channel_id),
        details=f"new_url={url}",
    )
    await state.clear()

    status_str = "🟢 Enabled" if channel.is_enabled else "🔴 Disabled"
    text = (
        "✅ **Channel Join URL Updated!**\n\n"
        f"• **Display Name:** `{channel.display_name}`\n"
        f"• **Channel ID:** `{channel.channel_id}`\n"
        f"• **Join URL:** `{channel.join_url}`\n"
        f"• **Status:** {status_str}\n"
    )
    await message.answer(text, reply_markup=build_channel_detail_keyboard(channel))


