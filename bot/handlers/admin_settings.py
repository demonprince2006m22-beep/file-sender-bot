"""Handlers for configuring global bot behavior, force-sub requirement, and delivery defaults."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_back_button,
    build_cancel_fsm_button,
    build_settings_menu_keyboard,
)
from bot.middlewares.auth_middleware import IsAdminFilter
from bot.services import AuditService
from bot.states.admin_states import SettingsEditStates

logger = logging.getLogger(__name__)

router = Router(name="admin_settings_router")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


@router.callback_query(F.data == "admin:settings")
async def handle_settings_menu_cb(
    callback: CallbackQuery, repo: Repository, state: FSMContext
) -> None:
    """View behavior settings."""
    await state.clear()
    force_sub_val = await repo.get_setting("force_sub_enabled", "true")
    force_sub = force_sub_val.lower() in ("true", "1", "yes")

    expiry_val = await repo.get_setting("default_expiry_hours", "0")
    limit_val = await repo.get_setting("default_delivery_limit", "0")
    autodel_val = await repo.get_setting("auto_delete_minutes", "0")

    expiry_desc = f"{expiry_val} hours" if expiry_val != "0" else "Permanent (No expiry)"
    limit_desc = f"{limit_val} per user" if limit_val != "0" else "Unlimited"
    autodel_desc = f"{autodel_val} minutes" if autodel_val != "0" else "🔴 Disabled (Files Kept)"

    text = (
        "⚙️ **Bot Behavior Settings**\n\n"
        f"• **Enforce Channel Subscription:** {'🟢 Enabled' if force_sub else '🔴 Disabled'}\n"
        f"• **Default Link Expiration:** `{expiry_desc}`\n"
        f"• **Default Download Limit:** `{limit_desc}`\n"
        f"• **Delivered File Auto-Delete:** `{autodel_desc}`\n\n"
        "Configure options below:"
    )

    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_settings_menu_keyboard(force_sub=force_sub)
        )
    await callback.answer()


@router.callback_query(F.data == "admin:set:toggle_forcesub")
async def handle_toggle_forcesub_cb(
    callback: CallbackQuery, repo: Repository, audit_service: AuditService
) -> None:
    """Toggle requirement for membership in all enabled channels."""
    current_val = await repo.get_setting("force_sub_enabled", "true")
    new_val = "false" if current_val.lower() in ("true", "1", "yes") else "true"
    await repo.set_setting("force_sub_enabled", new_val)

    await audit_service.log(
        admin_id=callback.from_user.id,
        action="toggle_force_sub",
        details=f"enabled={new_val}",
    )

    await callback.answer(f"Force subscription {'enabled' if new_val == 'true' else 'disabled'}.")

    # Refresh
    force_sub = new_val == "true"
    expiry_val = await repo.get_setting("default_expiry_hours", "0")
    limit_val = await repo.get_setting("default_delivery_limit", "0")
    autodel_val = await repo.get_setting("auto_delete_minutes", "0")
    expiry_desc = f"{expiry_val} hours" if expiry_val != "0" else "Permanent (No expiry)"
    limit_desc = f"{limit_val} per user" if limit_val != "0" else "Unlimited"
    autodel_desc = f"{autodel_val} minutes" if autodel_val != "0" else "🔴 Disabled (Files Kept)"

    text = (
        "⚙️ **Bot Behavior Settings**\n\n"
        f"• **Enforce Channel Subscription:** {'🟢 Enabled' if force_sub else '🔴 Disabled'}\n"
        f"• **Default Link Expiration:** `{expiry_desc}`\n"
        f"• **Default Download Limit:** `{limit_desc}`\n"
        f"• **Delivered File Auto-Delete:** `{autodel_desc}`\n\n"
        "Configure options below:"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_settings_menu_keyboard(force_sub=force_sub)
        )


@router.callback_query(F.data == "admin:set:expiry")
async def handle_edit_default_expiry_cb(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Prompt for default expiry hours."""
    await state.set_state(SettingsEditStates.waiting_for_expiry_hours)
    text = (
        "⏱ **Configure Default Link Expiration**\n\n"
        "Send the default expiration time in hours for newly uploaded files.\n"
        "Send `0` for links to never expire by default:"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button("admin:settings")
        )
    await callback.answer()


@router.message(SettingsEditStates.waiting_for_expiry_hours)
async def process_default_expiry_input(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Save default expiry hours."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.reply("❌ Please enter a positive integer or `0`.")
        return

    hours = int(raw)
    await repo.set_setting("default_expiry_hours", str(hours))
    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_default_expiry",
        details=f"hours={hours}",
    )
    await state.clear()

    await message.answer(
        f"✅ Default expiration set to `{hours}` hours.",
        reply_markup=build_back_button("admin:settings"),
    )


@router.callback_query(F.data == "admin:set:limit")
async def handle_edit_default_limit_cb(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Prompt for default delivery limit."""
    await state.set_state(SettingsEditStates.waiting_for_delivery_limit)
    text = (
        "🛑 **Configure Default Per-User Download Limit**\n\n"
        "Send the default maximum download count per user for newly uploaded files.\n"
        "Send `0` for unlimited downloads:"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button("admin:settings")
        )
    await callback.answer()


@router.message(SettingsEditStates.waiting_for_delivery_limit)
async def process_default_limit_input(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Save default delivery limit."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.reply("❌ Please enter a positive integer or `0`.")
        return

    limit = int(raw)
    await repo.set_setting("default_delivery_limit", str(limit))
    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_default_limit",
        details=f"limit={limit}",
    )
    await state.clear()

    await message.answer(
        f"✅ Default download limit set to `{limit}` per user.",
        reply_markup=build_back_button("admin:settings"),
    )


@router.callback_query(F.data == "admin:set:autodel")
async def handle_edit_default_autodel_cb(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Prompt for default auto-delete time in minutes."""
    await state.set_state(SettingsEditStates.waiting_for_auto_delete)
    text = (
        "🗑 **Configure Delivered File Auto-Delete**\n\n"
        "Delivered files in users' private chats will be automatically deleted after the specified time to protect copyrighted content.\n\n"
        "• Send the auto-delete time in **minutes** (e.g. `5`, `10`, `30`, `60`).\n"
        "• Send `0` to **disable** automatic file deletion:"
    )
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button("admin:settings")
        )
    await callback.answer()


@router.message(SettingsEditStates.waiting_for_auto_delete)
async def process_default_autodel_input(
    message: Message, state: FSMContext, repo: Repository, audit_service: AuditService
) -> None:
    """Save default auto-delete minutes."""
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.reply("❌ Please enter a positive integer or `0`.")
        return

    minutes = int(raw)
    await repo.set_setting("auto_delete_minutes", str(minutes))
    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_auto_delete",
        details=f"minutes={minutes}",
    )
    await state.clear()

    desc = f"`{minutes}` minutes" if minutes > 0 else "Disabled (files will not be auto-deleted)"
    await message.answer(
        f"✅ Delivered file auto-delete set to: {desc}.",
        reply_markup=build_back_button("admin:settings"),
    )

