"""Handlers for main Admin Panel navigation, statistics, and audit logs."""

import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_admin_main_menu,
    build_back_button,
)
from bot.middlewares.auth_middleware import IsAdminFilter

logger = logging.getLogger(__name__)

router = Router(name="admin_panel_router")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


@router.message(Command("panel"))
async def handle_panel_command(
    message: Message,
    repo: Repository,
    state: FSMContext,
) -> None:
    """Open Admin Control Panel."""
    await state.clear()
    user_id = message.from_user.id
    is_owner = await repo.is_owner(user_id)
    stats = await repo.get_overview_stats()

    text = (
        "👑 **Admin Control Panel**\n\n"
        "Manage file storage, required channels, message templates, and bot behavior.\n\n"
        f"📊 **Overview:**\n"
        f"• 📁 Stored Files: `{stats['total_files']}` (Active: `{stats['active_files']}`)\n"
        f"• 📢 Required Channels: `{stats['total_channels']}` (Enabled: `{stats['enabled_channels']}`)\n"
        f"• 🚀 Total Deliveries: `{stats['total_deliveries']}`\n\n"
        "Select a section below:"
    )
    await message.answer(text, reply_markup=build_admin_main_menu(is_owner=is_owner))


@router.callback_query(F.data == "admin:menu")
async def handle_admin_menu_callback(
    callback: CallbackQuery,
    repo: Repository,
    state: FSMContext,
) -> None:
    """Return to main admin menu."""
    await state.clear()
    user_id = callback.from_user.id
    is_owner = await repo.is_owner(user_id)
    stats = await repo.get_overview_stats()

    text = (
        "👑 **Admin Control Panel**\n\n"
        f"📊 **System Status:**\n"
        f"• 📁 Stored Files: `{stats['total_files']}` (Active: `{stats['active_files']}`)\n"
        f"• 📢 Required Channels: `{stats['total_channels']}` (Active: `{stats['enabled_channels']}`)\n"
        f"• 🚀 Deliveries: `{stats['total_deliveries']}` to `{stats['unique_users']}` users\n\n"
        "Select a section below:"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_admin_main_menu(is_owner=is_owner)
        )
    await callback.answer()


@router.callback_query(F.data == "admin:overview")
async def handle_overview_callback(
    callback: CallbackQuery,
    repo: Repository,
) -> None:
    """Display comprehensive system metrics and recent delivery activity."""
    stats = await repo.get_overview_stats()
    storage_ch = await repo.get_setting("storage_channel_id", "Not configured")
    recent_delivs = await repo.get_recent_deliveries(limit=5)

    deliv_lines = []
    for d in recent_delivs:
        fname = d.file_name or f"File #{d.file_id}"
        date_str = d.delivered_at.strftime("%Y-%m-%d %H:%M") if d.delivered_at else ""
        deliv_lines.append(f"• User `{d.user_id}` ➔ `{fname}` ({date_str})")

    deliv_text = "\n".join(deliv_lines) if deliv_lines else "_No deliveries recorded yet._"

    text = (
        "📊 **Detailed System Overview**\n\n"
        f"📁 **File Storage:**\n"
        f"• Total Files: `{stats['total_files']}`\n"
        f"• Active Links: `{stats['active_files']}`\n"
        f"• Disabled Links: `{stats['disabled_files']}`\n"
        f"• Deleted Records: `{stats['deleted_files']}`\n\n"
        f"📢 **Channels & Access:**\n"
        f"• Configured Channels: `{stats['total_channels']}`\n"
        f"• Enabled Channels: `{stats['enabled_channels']}`\n"
        f"• Storage Channel: `{storage_ch}`\n\n"
        f"🚀 **Deliveries & Users:**\n"
        f"• Total Deliveries: `{stats['total_deliveries']}`\n"
        f"• Unique Users: `{stats['unique_users']}`\n"
        f"• Total Admins: `{stats['admin_count']}`\n\n"
        f"🕒 **Recent Deliveries (Last 5):**\n"
        f"{deliv_text}"
    )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_back_button("admin:menu"))
    await callback.answer()


@router.callback_query(F.data == "admin:audit")
async def handle_audit_logs_callback(
    callback: CallbackQuery,
    repo: Repository,
) -> None:
    """Show recent administrative actions audit trail."""
    logs = await repo.get_recent_audit_logs(limit=12)

    log_lines = []
    for entry in logs:
        time_str = entry.created_at.strftime("%m-%d %H:%M") if entry.created_at else ""
        target_str = f" [{entry.target}]" if entry.target else ""
        details_str = f" ({entry.details})" if entry.details else ""
        log_lines.append(
            f"`{time_str}` Admin `{entry.admin_id}`: **{entry.action}**{target_str}{details_str}"
        )

    log_text = "\n".join(log_lines) if log_lines else "_No audit logs recorded yet._"

    text = (
        "📋 **Recent Admin Audit Logs (Last 12 Actions)**\n\n"
        f"{log_text}\n\n"
        "_Audit logs track configuration changes and file management actions without exposing secrets._"
    )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_back_button("admin:menu"))
    await callback.answer()


@router.callback_query(F.data == "admin:close")
async def handle_close_callback(callback: CallbackQuery) -> None:
    """Close and delete the admin panel message."""
    if callback.message:
        await callback.message.delete()
    await callback.answer("Admin panel closed.")


@router.callback_query(F.data == "noop")
async def handle_noop_callback(callback: CallbackQuery) -> None:
    """Acknowledge no-op callback clicks."""
    await callback.answer()

