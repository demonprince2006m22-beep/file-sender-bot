"""Handlers for owner-only admin allowlist management."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_admins_menu_keyboard,
    build_back_button,
    build_cancel_fsm_button,
    build_confirmation_keyboard,
)
from bot.middlewares.auth_middleware import IsOwnerFilter
from bot.services import AuditService
from bot.states.admin_states import AdminManageStates

logger = logging.getLogger(__name__)

router = Router(name="admin_manage_router")
# Strictly protected by IsOwnerFilter
router.message.filter(IsOwnerFilter())
router.callback_query.filter(IsOwnerFilter())


@router.callback_query(F.data == "admin:admins")
async def handle_admins_menu_cb(
    callback: CallbackQuery, repo: Repository, state: FSMContext
) -> None:
    """View list of authorized admins."""
    await state.clear()
    admins = await repo.list_admins()
    owner_id = callback.from_user.id

    text = (
        "👥 **Admin Allowlist Management (Owner Only)**\n\n"
        "Only the Bot Owner can add or revoke admin access.\n"
        "Admins have full access to upload files, manage channels, and view links.\n\n"
        f"Configured Admins (`{len(admins)}`):"
    )

    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=build_admins_menu_keyboard(admins, current_owner_id=owner_id),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:add_admin")
async def handle_add_admin_start_cb(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Prompt for new admin's numeric Telegram ID."""
    await state.set_state(AdminManageStates.waiting_for_admin_id)
    text = (
        "➕ **Add New Admin**\n\n"
        "Please send the numeric Telegram ID of the user you want to grant admin rights to.\n\n"
        "*(Note: You can ask them to send a message to @userinfobot to find their numeric ID.)*"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button("admin:admins")
        )
    await callback.answer()


@router.message(AdminManageStates.waiting_for_admin_id)
async def process_new_admin_id_input(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Process and save new admin ID."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.reply(
            "❌ Invalid ID. Please enter a valid numeric Telegram ID.",
            reply_markup=build_cancel_fsm_button("admin:admins"),
        )
        return

    new_admin_id = int(raw)
    owner_id = message.from_user.id

    if new_admin_id == owner_id:
        await message.reply("You are already the Owner!")
        return

    await repo.add_admin(telegram_id=new_admin_id, role="admin", added_by=owner_id)
    await audit_service.log(
        admin_id=owner_id,
        action="add_admin",
        target=str(new_admin_id),
    )
    await state.clear()

    admins = await repo.list_admins()
    await message.answer(
        f"✅ User ID `{new_admin_id}` is now granted **Admin** rights!",
        reply_markup=build_admins_menu_keyboard(admins, current_owner_id=owner_id),
    )


@router.callback_query(F.data.startswith("admin:rev_conf:"))
async def handle_revoke_admin_conf_cb(
    callback: CallbackQuery, repo: Repository
) -> None:
    """Show confirmation before revoking an admin."""
    target_id = int(callback.data.split(":", 2)[2])

    if await repo.is_owner(target_id):
        await callback.answer("Cannot revoke the Bot Owner!", show_alert=True)
        return

    text = (
        "⚠️ **Revoke Admin Privileges?**\n\n"
        f"Are you sure you want to remove user `{target_id}` from the admin allowlist?\n"
        "They will immediately lose access to the admin panel and file uploads."
    )
    confirm_data = f"admin:revoke:{target_id}"
    cancel_data = "admin:admins"

    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_confirmation_keyboard(confirm_data, cancel_data)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:revoke:"))
async def handle_revoke_admin_execute_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Execute removal of admin."""
    target_id = int(callback.data.split(":", 2)[2])
    owner_id = callback.from_user.id

    await repo.remove_admin(target_id)
    await audit_service.log(
        admin_id=owner_id,
        action="revoke_admin",
        target=str(target_id),
    )

    await callback.answer("Admin revoked successfully.", show_alert=True)
    admins = await repo.list_admins()
    if callback.message:
        await callback.message.edit_text(
            f"🚫 Admin `{target_id}` has been removed.",
            reply_markup=build_admins_menu_keyboard(admins, current_owner_id=owner_id),
        )

