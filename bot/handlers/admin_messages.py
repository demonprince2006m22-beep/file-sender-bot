"""Handlers for customizing bot message templates."""

import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import DEFAULT_MESSAGES
from bot.database.repository import Repository
from bot.keyboards.admin_kb import (
    build_back_button,
    build_cancel_fsm_button,
    build_template_actions_keyboard,
    build_templates_menu_keyboard,
)
from bot.middlewares.auth_middleware import IsAdminFilter
from bot.services import AuditService, MessageService
from bot.states.admin_states import TemplateEditStates

logger = logging.getLogger(__name__)

router = Router(name="admin_messages_router")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

PLACEHOLDERS_HELP = {
    "msg_welcome": "• `{first_name}` — User's Telegram first name\n• `{user_id}` — User's numeric ID",
    "msg_sub_prompt": "• `{first_name}` — User's first name\n• `{file_name}` — Name of requested file\n• `{file_size}` — Formatted size",
    "msg_success": "• `{first_name}` — User's first name\n• `{file_name}` — File name\n• `{file_size}` — File size",
    "msg_invalid_link": "• `{first_name}` — User's first name",
    "msg_disabled_link": "• `{first_name}` — User's first name",
    "msg_expired_link": "• `{first_name}` — User's first name",
    "msg_limit_reached": "• `{first_name}` — User's first name",
    "msg_auto_delete_notice": "• `{delete_time}` — Formatted time until auto-delete (e.g. 5 minutes)",
    "msg_help": "• `{first_name}` — User's first name",
}


@router.callback_query(F.data == "admin:templates")
async def handle_templates_menu_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """View list of message templates."""
    await state.clear()
    text = (
        "💬 **Customizable Bot Messages**\n\n"
        "You can customize all automated responses sent to users.\n"
        "Select a template below to view its content, preview formatting, or edit it:"
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_templates_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:tpl:"))
async def handle_template_view_cb(
    callback: CallbackQuery, message_service: MessageService, state: FSMContext
) -> None:
    """View a single template."""
    await state.clear()
    tpl_key = callback.data.split(":", 2)[2]
    raw_text = await message_service.get_raw_template(tpl_key)
    placeholders = PLACEHOLDERS_HELP.get(tpl_key, "_No specific placeholders_")

    text = (
        f"💬 **Template: `{tpl_key}`**\n\n"
        f"**Available Placeholders:**\n{placeholders}\n\n"
        "**Current Text:**\n"
        "```text\n"
        f"{raw_text}\n"
        "```"
    )

    if callback.message:
        await callback.message.edit_text(text, reply_markup=build_template_actions_keyboard(tpl_key))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:tpledit:"))
async def handle_template_edit_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt user to send new template text."""
    tpl_key = callback.data.split(":", 2)[2]
    await state.update_data(tpl_key=tpl_key)
    await state.set_state(TemplateEditStates.waiting_for_template_text)

    placeholders = PLACEHOLDERS_HELP.get(tpl_key, "")
    text = (
        f"✏️ **Edit Template: `{tpl_key}`**\n\n"
        f"Supported Placeholders:\n{placeholders}\n\n"
        "Please send the new message text now (Markdown is supported):"
    )

    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=build_cancel_fsm_button(f"admin:tpl:{tpl_key}")
        )
    await callback.answer()


@router.message(TemplateEditStates.waiting_for_template_text)
async def process_new_template_text(
    message: Message,
    state: FSMContext,
    repo: Repository,
    audit_service: AuditService,
) -> None:
    """Save new template text."""
    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.reply("❌ Message text cannot be empty.")
        return

    data = await state.get_data()
    tpl_key = data["tpl_key"]

    await repo.set_setting(tpl_key, new_text)
    await audit_service.log(
        admin_id=message.from_user.id,
        action="update_template",
        target=tpl_key,
    )
    await state.clear()

    await message.answer(
        f"✅ Template `{tpl_key}` has been updated successfully!",
        reply_markup=build_back_button(f"admin:tpl:{tpl_key}"),
    )


@router.callback_query(F.data.startswith("admin:tplreset:"))
async def handle_template_reset_cb(
    callback: CallbackQuery,
    repo: Repository,
    audit_service: AuditService,
) -> None:
    """Reset template to built-in default."""
    tpl_key = callback.data.split(":", 2)[2]
    default_text = DEFAULT_MESSAGES.get(tpl_key)

    if not default_text:
        await callback.answer("No default exists for this template.", show_alert=True)
        return

    await repo.set_setting(tpl_key, default_text)
    await audit_service.log(
        admin_id=callback.from_user.id,
        action="reset_template",
        target=tpl_key,
    )

    await callback.answer("Template reset to default!", show_alert=True)
    if callback.message:
        await callback.message.edit_text(
            f"✅ Template `{tpl_key}` was reset to default.",
            reply_markup=build_back_button(f"admin:tpl:{tpl_key}"),
        )

