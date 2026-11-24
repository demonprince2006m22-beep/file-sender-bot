"""Finite State Machine (FSM) states for Admin Panel interactions."""

from aiogram.fsm.state import State, StatesGroup


class AddChannelStates(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_display_name = State()
    waiting_for_join_url = State()


class EditChannelStates(StatesGroup):
    waiting_for_display_name = State()
    waiting_for_join_url = State()


class StorageChannelStates(StatesGroup):
    waiting_for_storage_channel_id = State()


class TemplateEditStates(StatesGroup):
    waiting_for_template_text = State()


class SettingsEditStates(StatesGroup):
    waiting_for_expiry_hours = State()
    waiting_for_delivery_limit = State()
    waiting_for_auto_delete = State()


class FileManageStates(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_custom_expiry = State()
    waiting_for_custom_limit = State()
    waiting_for_custom_autodel = State()


class AdminManageStates(StatesGroup):
    waiting_for_admin_id = State()

