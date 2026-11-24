"""Handlers for managing stored files, links, expirations, and delivery limits."""

import logging
from datetime import datetime, timedelta, timezone
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_back_button,
    build_cancel_fsm_button,
    build_confirmation_keyboard,
    build_file_detail_keyboard,
    build_files_list_keyboard,
)
from bot.middlewares.auth_middleware import IsAdminFilter
from bot.services import (
    AuditService,
    format_file_size,
    generate_secure_token,
)
from bot.states.admin_states import FileManageStates

logger = logging.getLogger(__name__)

router = Router(name="admin_files_router")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

PAGE_SIZE = 8


# ==================== COMMANDS ====================


@router.message(Command("files"))
async def handle_files_command(message: Message, repo: Repository, state: FSMContext) -> None:
    """List stored files command."""
    await state.clear()
    files, total = await repo.list_files(limit=PAGE_SIZE, offset=0)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    text = (
        "📁 **Stored Files Manager**\n\n"
        f"Total Files in Database: `{total}`\n"
        "Click on a file to view deep links, change limits, toggle status, or regenerate links:"
    )
    await message.answer(
        text,
        reply_markup=build_files_list_keyboard(
            files=files, page=0, total_pages=total_pages
        ),
    )


@router.message(Command("disable"))
async def handle_disable_command(
    message: Message, repo: Repository, audit_service: AuditService
) -> None:
    """Quick command to disable a file link: /disable <file_id> or /disable <token>."""
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.reply("Usage: `/disable <file_id_or_token>`")
        return

    arg = parts[1].strip()
    file = None
    if arg.isdigit():
        file = await repo.get_file_by_id(int(arg))
    if not file:
        file = await repo.get_file_by_token(arg)

    if not file:
        await message.reply(f"❌ File record matching '{arg}' not found.")
        return

    await repo.update_file_status(file.id, "disabled")
    await audit_service.log(
        admin_id=message.from_user.id,
        action="disable_file_cmd",
        target=str(file.id),
        details=f"token={file.link_token}",
    )
    await message.reply(f"🚫 File `{file.file_name or file.id}` link is now **Disabled**.")


# ==================== CALLBACKS ====================


@router.callback_query(F.data.startswith("admin:files:p:"))
async def handle_files_pagination_cb(
    callback: CallbackQuery, repo: Repository, state: FSMContext
) -> None:
    """Paginated files browser."""
    page = int(callback.data.split(":", 3)[3])
    data = await state.get_data()
    search = data.get("search")

    offset = page * PAGE_SIZE
    files, total = await repo.list_files(limit=PAGE_SIZE, offset=offset, search=search)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    search_notice = f"\n🔍 Filtered by: `{search}`" if search else ""
    text = (
        "📁 **Stored Files Manager**\n\n"
        f"Total Files: `{total}`{search_notice}\n"
        "Click on a file below to manage its settings:"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=build_files_list_keyboard(
                files=files, page=page, total_pages=total_pages, search=search
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:files:search")
async def handle_files_search_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Start file search."""
    data = await state.get_data()
    if data.get("search"):
        # If search was already active, clicking clears it
        await state.update_data(search=None)
        await callback.answer("Search filter cleared.")
        # Re-render page 0
        from bot.handlers.admin_files import handle_files_pagination_cb
        callback.data = "admin:files:p:0"
        return

    await state.set_state(FileManageStates.waiting_for_search_query)
    text = "🔍 **Search Files**\n\nSend a keyword to search by filename or token:"
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_cancel_fsm_button("admin:files:p:0"))
    await callback.answer()


@router.message(FileManageStates.waiting_for_search_query)
async def process_file_search_input(
    message: Message, state: FSMContext, repo: Repository
) -> None:
    """Process search keyword and show results."""
    query = (message.text or "").strip()
    await state.update_data(search=query)
    await state.set_state(None)

    files, total = await repo.list_files(limit=PAGE_SIZE, offset=0, search=query)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    text = (
        "🔍 **Search Results**\n\n"
        f"Matches for `{query}`: `{total}`\n"
        "Select a file to manage:"
    )
    await message.answer(
        text,
        reply_markup=build_files_list_keyboard(
            files=files, page=0, total_pages=total_pages, search=query
        ),
    )


@router.callback_query(F.data.startswith("admin:file:view:"))
async def handle_file_view_cb(
    callback: CallbackQuery, bot: Bot, repo: Repository, state: FSMContext
) -> None:
    """View file details, share link, and management options."""
    await state.clear()
    file_id = int(callback.data.split(":", 3)[3])
    file = await repo.get_file_by_id(file_id)

    if not file:
        await callback.answer("File record not found.", show_alert=True)
        return

    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start={file.link_token}"

    status_icon = "🟢 Active" if file.status == "active" else ("🟡 Disabled" if file.status == "disabled" else "🔴 Deleted")
    created_str = file.created_at.strftime("%Y-%m-%d %H:%M") if file.created_at else "Unknown"

    expiry_str = "None (Permanent)"
    if file.expires_at:
        is_exp = file.is_expired()
        expiry_str = f"{file.expires_at.strftime('%Y-%m-%d %H:%M UTC')} {'(⚠️ Expired)' if is_exp else ''}"

    limit_str = f"{file.delivery_limit} downloads per user" if file.delivery_limit else "Unlimited"

    global_autodel = await repo.get_setting("auto_delete_minutes", "0")
    if file.auto_delete_minutes is not None:
        if file.auto_delete_minutes == 0:
            autodel_str = "🔴 Never (Custom: Disabled)"
        else:
            autodel_str = f"⏱ {file.auto_delete_minutes} minutes (Custom)"
    else:
        autodel_str = (
            f"🌐 Global Default ({global_autodel} min)"
            if global_autodel != "0"
            else "🌐 Global Default (Disabled)"
        )

    text = (
        f"📁 **File Details (ID: #{file.id})**\n\n"
        f"• **Name:** `{file.file_name or 'Unnamed file'}`\n"
        f"• **Size:** `{format_file_size(file.file_size)}`\n"
        f"• **Type:** `{file.media_type}`\n"
        f"• **Status:** {status_icon}\n"
        f"• **Deliveries:** `{file.delivery_count}` times\n"
        f"• **Uploaded:** `{created_str}`\n"
        f"• **Expiration:** `{expiry_str}`\n"
        f"• **Delivery Limit:** `{limit_str}`\n"
        f"• **Auto-Delete:** `{autodel_str}`\n\n"
        f"🔗 **Access Deep Link:**\n"
        f"`{deep_link}`\n"
    )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_file_detail_keyboard(file))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:file:toggle:"))
async def handle_file_toggle_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Toggle file active/disabled."""
    file_id = int(callback.data.split(":", 3)[3])
    file = await repo.get_file_by_id(file_id)
    if not file:
        await callback.answer("File not found.", show_alert=True)
        return

    new_status = "disabled" if file.status == "active" else "active"
    await repo.update_file_status(file_id, new_status)
    await audit_service.log(
        admin_id=callback.from_user.id,
        action="toggle_file_status",
        target=str(file_id),
        details=f"new_status={new_status}",
    )

    await callback.answer(f"File marked as {new_status}.")
    # Refresh file view
    callback.data = f"admin:file:view:{file_id}"
    from bot.handlers.admin_files import handle_file_view_cb
    # Will trigger view refresh


@router.callback_query(F.data.startswith("admin:file:regen:"))
async def handle_file_regenerate_token_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Regenerate link token (invalidates old link)."""
    file_id = int(callback.data.split(":", 3)[3])
    file = await repo.get_file_by_id(file_id)
    if not file:
        await callback.answer("File not found.", show_alert=True)
        return

    old_token = file.link_token
    new_token = generate_secure_token()
    await repo.update_file_token(file_id, new_token)

    await audit_service.log(
        admin_id=callback.from_user.id,
        action="regenerate_file_token",
        target=str(file_id),
        details=f"old_token={old_token[:6]}..., new_token={new_token[:6]}...",
    )

    await callback.answer("🔑 Link token regenerated! Old link is now invalid.", show_alert=True)


@router.callback_query(F.data.startswith("admin:file:expiry:"))
async def handle_file_set_expiry_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt for file expiration."""
    file_id = int(callback.data.split(":", 3)[3])
    await state.update_data(file_id=file_id)
    await state.set_state(FileManageStates.waiting_for_custom_expiry)

    text = (
        "⏱ **Set Link Expiration**\n\n"
        "Send the number of hours this link should remain active (e.g. `24` for 1 day, `72` for 3 days).\n"
        "Send `0` to remove expiration (never expires):"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_cancel_fsm_button(f"admin:file:view:{file_id}"))
    await callback.answer()


@router.message(FileManageStates.waiting_for_custom_expiry)
async def process_file_custom_expiry(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Process expiration hours."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.reply("❌ Please enter a positive integer or `0`.")
        return

    hours = int(raw)
    data = await state.get_data()
    file_id = data["file_id"]

    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours) if hours > 0 else None
    await repo.update_file_expiry(file_id, expires_at)

    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_file_expiry",
        target=str(file_id),
        details=f"hours={hours}",
    )
    await state.clear()

    exp_text = f"expires in {hours} hours" if hours > 0 else "will never expire"
    await message.answer(f"✅ Expiration updated: link {exp_text}.", reply_markup=build_back_button(f"admin:file:view:{file_id}"))


@router.callback_query(F.data.startswith("admin:file:limit:"))
async def handle_file_set_limit_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt for delivery limit."""
    file_id = int(callback.data.split(":", 3)[3])
    await state.update_data(file_id=file_id)
    await state.set_state(FileManageStates.waiting_for_custom_limit)

    text = (
        "🛑 **Set Per-User Delivery Limit**\n\n"
        "Send the maximum number of times each user can download this file (e.g. `1` for one-time access).\n"
        "Send `0` to remove limit (unlimited):"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_cancel_fsm_button(f"admin:file:view:{file_id}"))
    await callback.answer()


@router.message(FileManageStates.waiting_for_custom_limit)
async def process_file_custom_limit(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Process delivery limit."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.reply("❌ Please enter a positive integer or `0`.")
        return

    limit = int(raw)
    data = await state.get_data()
    file_id = data["file_id"]

    val = limit if limit > 0 else None
    await repo.update_file_delivery_limit(file_id, val)

    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_file_limit",
        target=str(file_id),
        details=f"limit={limit}",
    )
    await state.clear()

    limit_text = f"{limit} download(s) per user" if limit > 0 else "unlimited"
    await message.answer(f"✅ Delivery limit updated: {limit_text}.", reply_markup=build_back_button(f"admin:file:view:{file_id}"))


@router.callback_query(F.data.startswith("admin:file:autodel:"))
async def handle_file_set_autodel_cb(
    callback: CallbackQuery, state: FSMContext, repo: Repository
) -> None:
    """Prompt for file-specific auto-delete timer."""
    file_id = int(callback.data.split(":", 3)[3])
    file = await repo.get_file_by_id(file_id)
    if not file:
        await callback.answer("File not found.", show_alert=True)
        return

    await state.update_data(file_id=file_id)
    await state.set_state(FileManageStates.waiting_for_custom_autodel)

    text = (
        "🗑 **Set File Auto-Delete Timer**\n\n"
        f"File: `{file.file_name or file.id}`\n\n"
        "Delivered messages in users' chats will be automatically deleted after this duration:\n\n"
        "• Send the number of **minutes** (e.g. `5`, `10`, `30`, `60`).\n"
        "• Send `0` to **NEVER** delete this file.\n"
        "• Send `-1` to revert to **Global Default** setting:"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_cancel_fsm_button(f"admin:file:view:{file_id}"))
    await callback.answer()


@router.message(FileManageStates.waiting_for_custom_autodel)
async def process_file_custom_autodel(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Process custom auto-delete input."""
    raw = (message.text or "").strip()
    try:
        val = int(raw)
    except ValueError:
        await message.reply(
            "❌ Please enter a valid integer: minutes (e.g. `5`, `10`), `0` for never, or `-1` for global default."
        )
        return

    data = await state.get_data()
    file_id = data["file_id"]

    if val < -1:
        await message.reply("❌ Invalid value. Enter 0, positive minutes, or -1.")
        return

    auto_delete_minutes = None if val == -1 else val
    await repo.update_file_auto_delete(file_id, auto_delete_minutes)

    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_file_auto_delete",
        target=str(file_id),
        details=f"minutes={auto_delete_minutes}",
    )
    await state.clear()

    if val == -1:
        result_text = "reverted to Global Default setting"
    elif val == 0:
        result_text = "set to NEVER auto-delete (Disabled)"
    else:
        result_text = f"set to auto-delete after `{val}` minutes"

    await message.answer(
        f"✅ File auto-delete {result_text}.",
        reply_markup=build_back_button(f"admin:file:view:{file_id}"),
    )


@router.callback_query(F.data.startswith("admin:file:del_conf:"))
async def handle_file_del_confirm_cb(callback: CallbackQuery, repo: Repository) -> None:
    """Show confirmation before deleting file record."""
    file_id = int(callback.data.split(":", 3)[3])
    file = await repo.get_file_by_id(file_id)

    if not file:
        await callback.answer("File not found.", show_alert=True)
        return

    text = (
        "⚠️ **Are you sure you want to delete this file record?**\n\n"
        f"• **File:** `{file.file_name or file.id}`\n"
        f"• **Token:** `{file.link_token}`\n\n"
        "The access link will immediately stop functioning for all users."
    )
    confirm_data = f"admin:file:del_exec:{file_id}"
    cancel_data = f"admin:file:view:{file_id}"
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_confirmation_keyboard(confirm_data, cancel_data)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:file:del_exec:"))
async def handle_file_del_execute_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Execute deletion of file record."""
    file_id = int(callback.data.split(":", 3)[3])
    await repo.delete_file(file_id)

    await audit_service.log(
        admin_id=callback.from_user.id,
        action="delete_file",
        target=str(file_id),
    )

    await callback.answer("File record deleted.", show_alert=True)
    if callback.message:
        await callback.message.edit_text(
            "🗑 **File Record Deleted**\n\nThe access link is now deactivated.",
            reply_markup=build_back_button("admin:files:p:0"),
        )

