"""Keyboards package initialization."""

from bot.keyboards.admin_kb import (
    build_admin_main_menu,
    build_admins_menu_keyboard,
    build_back_button,
    build_cancel_fsm_button,
    build_channel_detail_keyboard,
    build_channels_list_keyboard,
    build_confirmation_keyboard,
    build_file_detail_keyboard,
    build_files_list_keyboard,
    build_settings_menu_keyboard,
    build_storage_menu_keyboard,
    build_template_actions_keyboard,
    build_templates_menu_keyboard,
)
from bot.keyboards.user_kb import build_subscription_keyboard

__all__ = [
    "build_subscription_keyboard",
    "build_admin_main_menu",
    "build_back_button",
    "build_cancel_fsm_button",
    "build_confirmation_keyboard",
    "build_channels_list_keyboard",
    "build_channel_detail_keyboard",
    "build_storage_menu_keyboard",
    "build_files_list_keyboard",
    "build_file_detail_keyboard",
    "build_templates_menu_keyboard",
    "build_template_actions_keyboard",
    "build_settings_menu_keyboard",
    "build_admins_menu_keyboard",
]

