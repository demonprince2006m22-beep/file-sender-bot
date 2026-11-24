"""Handlers package initialization."""

from bot.handlers.admin_channels import router as admin_channels_router
from bot.handlers.admin_files import router as admin_files_router
from bot.handlers.admin_manage import router as admin_manage_router
from bot.handlers.admin_messages import router as admin_messages_router
from bot.handlers.admin_panel import router as admin_panel_router
from bot.handlers.admin_settings import router as admin_settings_router
from bot.handlers.admin_upload import router as admin_upload_router
from bot.handlers.user import router as user_router

__all__ = [
    "user_router",
    "admin_upload_router",
    "admin_panel_router",
    "admin_channels_router",
    "admin_storage_router",
    "admin_files_router",
    "admin_messages_router",
    "admin_settings_router",
    "admin_manage_router",
]

