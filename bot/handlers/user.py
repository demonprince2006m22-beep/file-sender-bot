"""Handlers for end-user commands, file requests, and membership verification."""

import logging
from typing import Optional
from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import FileRecord
from bot.database.repository import Repository
from bot.keyboards.admin_kb import build_admin_main_menu
from bot.keyboards.user_kb import build_subscription_keyboard
from bot.services import (
    AutoDeleteService,
    ChannelService,
    FileAccessStatus,
    FileService,
    MessageService,
    format_delete_time,
    format_file_size,
)

logger = logging.getLogger(__name__)

router = Router(name="user_router")


def build_delivery_caption(file_caption: Optional[str], success_text: str) -> str:
    """Build caption combining original media caption and success message template."""
    clean_success = (success_text or "").strip()
    clean_file_caption = (file_caption or "").strip()

    if not clean_file_caption:
        caption = clean_success
    elif clean_file_caption == clean_success:
        caption = clean_success
    else:
        caption = f"{clean_file_caption}\n\n{clean_success}"

    if len(caption) > 1024:
        if len(clean_success) <= 1024:
            available = 1024 - len(clean_success) - 5
            if available > 10:
                caption = f"{clean_file_caption[:available].strip()}...\n\n{clean_success}"
            else:
                caption = clean_success[:1024]
        else:
            caption = clean_success[:1020] + "..."

    if len(caption) > 1024:
        caption = caption[:1024]

    return caption


@router.message(CommandStart(deep_link=True))
async def handle_start_deep_link(
    message: Message,
    bot: Bot,
    repo: Repository,
    file_service: FileService,
    channel_service: ChannelService,
    message_service: MessageService,
    auto_delete_service: AutoDeleteService,
    state: FSMContext,
) -> None:
    """Handle /start <payload> - file delivery request."""
    await state.clear()
    token = message.text.split(maxsplit=1)[1].strip() if message.text else ""
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    await process_file_request(
        token=token,
        user_id=user_id,
        first_name=first_name,
        bot=bot,
        repo=repo,
        file_service=file_service,
        channel_service=channel_service,
        message_service=message_service,
        auto_delete_service=auto_delete_service,
        reply_to_message=message,
    )


@router.message(CommandStart(deep_link=False))
async def handle_start_regular(
    message: Message,
    repo: Repository,
    message_service: MessageService,
    state: FSMContext,
) -> None:
    """Handle plain /start without deep link argument."""
    await state.clear()
    user_id = message.from_user.id

    # If sender is an authorized admin, display the admin dashboard directly
    if await repo.is_admin(user_id):
        is_owner = await repo.is_owner(user_id)
        stats = await repo.get_overview_stats()
        text = (
            f"👑 **Admin Control Panel**\n\n"
            f"Welcome back, {message.from_user.first_name or 'Admin'}!\n\n"
            f"📊 **Current System Status:**\n"
            f"• 📁 Stored Files: `{stats['total_files']}` (Active: `{stats['active_files']}`)\n"
            f"• 📢 Required Channels: `{stats['total_channels']}` (Active: `{stats['enabled_channels']}`)\n"
            f"• 🚀 Total Deliveries: `{stats['total_deliveries']}`\n\n"
            f"Choose an option below to manage the bot, or send any file to store it:"
        )
        await message.answer(text, reply_markup=build_admin_main_menu(is_owner=is_owner))
        return

    # Regular user welcome message
    welcome_text = await message_service.render(
        "msg_welcome",
        first_name=message.from_user.first_name or "Friend",
        user_id=user_id,
    )
    await message.answer(welcome_text)


@router.message(Command("help"))
async def handle_help_command(
    message: Message,
    repo: Repository,
    message_service: MessageService,
) -> None:
    """Handle /help command."""
    user_id = message.from_user.id
    if await repo.is_admin(user_id):
        is_owner = await repo.is_owner(user_id)
        help_text = (
            "🛠 **Admin Commands Guide**\n\n"
            "• `/panel` or `/start` — Open main Admin Control Panel\n"
            "• `/files` — View and search stored files\n"
            "• `/channels` — Manage required subscription channels\n"
            "• `/addchannel` — Quick-add a required channel\n"
            "• `/removechannel` — Quick-remove a required channel\n"
            "• `/disable <file_id>` — Quickly disable a file link\n"
            "• `/help` — Show this help message\n\n"
            "**Uploading Files:**\n"
            "Simply send or forward any document, video, audio, or photo directly to the bot. "
            "The bot will automatically store it in the private storage channel and generate a secure access link."
        )
        if is_owner:
            help_text += "\n\n👑 *You are the Owner and have permission to manage additional admin IDs.*"
        await message.answer(help_text)
        return

    # Normal user help
    user_help = await message_service.render(
        "msg_help",
        first_name=message.from_user.first_name or "Friend",
        user_id=user_id,
    )
    await message.answer(user_help)


@router.callback_query(F.data.startswith("sub_verify:"))
async def handle_sub_verify_callback(
    callback: CallbackQuery,
    bot: Bot,
    repo: Repository,
    file_service: FileService,
    channel_service: ChannelService,
    message_service: MessageService,
    auto_delete_service: AutoDeleteService,
) -> None:
    """Handle user clicking 'Check again' to verify required channel subscriptions."""
    token = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "User"

    # 1. Evaluate file access
    status, file = await file_service.evaluate_access(token, user_id)
    if status != FileAccessStatus.ALLOWED or not file:
        await callback.answer("⚠️ Link is no longer valid or accessible.", show_alert=True)
        error_msg_key = {
            FileAccessStatus.NOT_FOUND: "msg_invalid_link",
            FileAccessStatus.DISABLED: "msg_disabled_link",
            FileAccessStatus.DELETED: "msg_invalid_link",
            FileAccessStatus.EXPIRED: "msg_expired_link",
            FileAccessStatus.LIMIT_REACHED: "msg_limit_reached",
        }.get(status, "msg_invalid_link")
        text = await message_service.render(error_msg_key, first_name=first_name)
        if callback.message:
            await callback.message.edit_text(text)
        return

    # 2. Check channel memberships
    all_joined, missing = await channel_service.check_user_membership(bot, user_id)

    if not all_joined:
        await callback.answer(
            f"❌ You have not joined all channels yet! ({len(missing)} remaining)",
            show_alert=True,
        )
        return

    # 3. All channels joined: Deliver file!
    await callback.answer("✅ Verification successful! Sending file...")

    try:
        success_text = await message_service.render(
            "msg_success",
            first_name=first_name,
            file_name=file.file_name or "file",
            file_size=format_file_size(file.file_size),
        )
        caption = build_delivery_caption(file.caption, success_text)

        sent_msg = await file_service.deliver_file_to_user(
            bot=bot,
            user_id=user_id,
            file=file,
            caption=caption,
        )

        # Clean up the verification prompt message if present
        if callback.message:
            try:
                await callback.message.delete()
            except Exception:
                pass

        await handle_delivery_auto_delete(
            bot=bot,
            repo=repo,
            auto_delete_service=auto_delete_service,
            message_service=message_service,
            user_id=user_id,
            file=file,
            file_message=sent_msg,
        )

    except Exception as e:
        logger.error("Error delivering file to user %s: %s", user_id, e)
        if callback.message:
            await callback.message.answer(
                "❌ An error occurred while retrieving your file. Please contact support."
            )


@router.callback_query(F.data.startswith("fsm:cancel:"))
async def handle_cancel_fsm_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    """Universal FSM cancel button callback."""
    target = callback.data.split(":", 2)[2]
    await state.clear()
    await callback.answer("Action cancelled.")

    if target == "admin:menu":
        from bot.keyboards.admin_kb import build_admin_main_menu
        # Need repo to check if owner
        # Just answer and edit message to main panel prompt
        await callback.message.edit_text(
            "👑 **Admin Control Panel**\n\nAction cancelled.",
            reply_markup=build_admin_main_menu(is_owner=True),
        )
    elif callback.message:
        await callback.message.delete()


async def process_file_request(
    token: str,
    user_id: int,
    first_name: str,
    bot: Bot,
    repo: Repository,
    file_service: FileService,
    channel_service: ChannelService,
    message_service: MessageService,
    auto_delete_service: AutoDeleteService,
    reply_to_message: Message,
) -> None:
    """Common logic for processing a file link request."""
    # 1. Evaluate file access
    status, file = await file_service.evaluate_access(token, user_id)

    if status == FileAccessStatus.NOT_FOUND:
        text = await message_service.render("msg_invalid_link", first_name=first_name)
        await reply_to_message.answer(text)
        return

    if status == FileAccessStatus.DISABLED:
        text = await message_service.render("msg_disabled_link", first_name=first_name)
        await reply_to_message.answer(text)
        return

    if status == FileAccessStatus.DELETED:
        text = await message_service.render("msg_invalid_link", first_name=first_name)
        await reply_to_message.answer(text)
        return

    if status == FileAccessStatus.EXPIRED:
        text = await message_service.render("msg_expired_link", first_name=first_name)
        await reply_to_message.answer(text)
        return

    if status == FileAccessStatus.LIMIT_REACHED:
        text = await message_service.render("msg_limit_reached", first_name=first_name)
        await reply_to_message.answer(text)
        return

    assert file is not None

    # 2. Check channel memberships
    all_joined, missing = await channel_service.check_user_membership(bot, user_id)

    if not all_joined:
        # Prompt subscription
        prompt_text = await message_service.render(
            "msg_sub_prompt",
            first_name=first_name,
            file_name=file.file_name or "Requested File",
            file_size=format_file_size(file.file_size),
        )
        check_btn_text = await repo.get_setting("btn_check_again", "🔄 Check again")
        join_btn_tpl = await repo.get_setting("btn_join_channel", "📢 Join {channel_name}")

        keyboard = build_subscription_keyboard(
            missing_channels=missing,
            token=token,
            check_button_text=check_btn_text,
            join_button_template=join_btn_tpl,
        )
        await reply_to_message.answer(prompt_text, reply_markup=keyboard)
        return

    # 3. All joined: Send the file!
    try:
        success_text = await message_service.render(
            "msg_success",
            first_name=first_name,
            file_name=file.file_name or "file",
            file_size=format_file_size(file.file_size),
        )
        caption = build_delivery_caption(file.caption, success_text)

        sent_msg = await file_service.deliver_file_to_user(
            bot=bot,
            user_id=user_id,
            file=file,
            caption=caption,
        )

        await handle_delivery_auto_delete(
            bot=bot,
            repo=repo,
            auto_delete_service=auto_delete_service,
            message_service=message_service,
            user_id=user_id,
            file=file,
            file_message=sent_msg,
        )
    except Exception as e:
        logger.error("Failed to deliver file to user %s: %s", user_id, e)
        await reply_to_message.answer(
            "❌ Failed to retrieve your file from storage. Please notify the administrator."
        )


async def handle_delivery_auto_delete(
    bot: Bot,
    repo: Repository,
    auto_delete_service: AutoDeleteService,
    message_service: MessageService,
    user_id: int,
    file: FileRecord,
    file_message: Optional[Message],
    notice_message: Optional[Message] = None,
) -> None:
    """Schedule auto-deletion for delivered file and notice messages if enabled."""
    try:
        if file.auto_delete_minutes is not None:
            minutes = file.auto_delete_minutes
        else:
            global_str = await repo.get_setting("auto_delete_minutes", "0")
            try:
                minutes = int(global_str)
            except ValueError:
                minutes = 0

        if minutes <= 0:
            return

        delay_seconds = minutes * 60
        time_str = format_delete_time(minutes)

        notice_text = await message_service.render(
            "msg_auto_delete_notice", delete_time=time_str
        )
        warn_msg = await bot.send_message(chat_id=user_id, text=notice_text)

        if file_message and getattr(file_message, "message_id", None):
            await auto_delete_service.schedule_deletion(
                bot=bot,
                chat_id=user_id,
                message_id=file_message.message_id,
                delay_seconds=delay_seconds,
            )

        if warn_msg and getattr(warn_msg, "message_id", None):
            await auto_delete_service.schedule_deletion(
                bot=bot,
                chat_id=user_id,
                message_id=warn_msg.message_id,
                delay_seconds=delay_seconds,
            )

        if notice_message and getattr(notice_message, "message_id", None):
            await auto_delete_service.schedule_deletion(
                bot=bot,
                chat_id=user_id,
                message_id=notice_message.message_id,
                delay_seconds=delay_seconds,
            )
    except Exception as e:
        logger.error("Error setting up auto-deletion for user %s: %s", user_id, e)


