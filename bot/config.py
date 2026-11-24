"""Configuration management for File Sender Bot."""

from pathlib import Path
from typing import List, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MESSAGES = {
    "msg_welcome": (
        "👋 **Welcome to File Sender Bot!**\n\n"
        "I provide access to secure files shared via special deep links.\n"
        "If you were sent a link, tap it to retrieve your file.\n\n"
        "Use /help if you need assistance."
    ),
    "msg_sub_prompt": (
        "⚠️ **Subscription Required**\n\n"
        "To access `{file_name}`, you must join our required channel(s) below:\n\n"
        "After joining all channels, click the **Check again** button below to get your file!"
    ),
    "msg_success": (
        "✅ **Here is your file, {first_name}!**\n\n"
        "📁 **File:** `{file_name}`\n"
        "📊 **Size:** `{file_size}`\n\n"
        "Thank you for using our service."
    ),
    "msg_invalid_link": (
        "❌ **Invalid or Unknown Link**\n\n"
        "This link does not exist or has been removed. Please check the link and try again."
    ),
    "msg_disabled_link": (
        "🚫 **Link Disabled**\n\n"
        "This file link has been temporarily disabled by administrators."
    ),
    "msg_expired_link": (
        "⌛ **Link Expired**\n\n"
        "This file link has expired and is no longer available."
    ),
    "msg_limit_reached": (
        "🛑 **Delivery Limit Reached**\n\n"
        "You have reached the maximum allowed downloads for this file link."
    ),
    "msg_help": (
        "ℹ️ **File Sender Bot Help**\n\n"
        "**How to get a file:**\n"
        "1. Click the file access link you received.\n"
        "2. If requested, join each of the required channels.\n"
        "3. Click **🔄 Check again** to verify membership.\n"
        "4. Your file will be delivered directly here!"
    ),
    "msg_auto_delete_notice": (
        "⏳ **Self-Destruct Notice**\n\n"
        "This file will be automatically deleted in **{delete_time}**!\n"
        "Please forward or save it to your **Saved Messages** before it expires."
    ),
    "btn_check_again": "🔄 Check again",
    "btn_join_channel": "📢 Join {channel_name}",
}


class Settings(BaseSettings):
    """Bot application settings."""

    BOT_TOKEN: str = Field(..., description="Telegram Bot API Token")
    OWNER_ID: int = Field(..., description="Telegram numeric ID of Bot Owner")
    ADMIN_IDS: Union[str, List[int]] = Field(default_factory=list, description="Additional Admin Telegram numeric IDs")
    STORAGE_CHANNEL_ID: Optional[int] = Field(default=None, description="Storage Channel ID (e.g. -100xxx)")
    DATABASE_PATH: Path = Field(default=Path("data/bot.db"), description="Path to SQLite database")
    DEFAULT_EXPIRY_HOURS: int = Field(default=0, description="Default link expiry in hours (0 = never)")
    DEFAULT_DELIVERY_LIMIT: int = Field(default=0, description="Default per-user download limit (0 = unlimited)")
    DEFAULT_AUTO_DELETE_MINUTES: int = Field(default=0, description="Default auto-delete time in minutes (0 = disabled)")
    FORCE_SUB_ENABLED: bool = Field(default=True, description="Enforce subscription to required channels")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        elif isinstance(v, (list, tuple, set)):
            return [int(x) for x in v]
        elif isinstance(v, int):
            return [v]
        return []

    @field_validator("STORAGE_CHANNEL_ID", mode="before")
    @classmethod
    def parse_storage_channel(cls, v):
        if v is None or v == "":
            return None
        return int(v)


def get_settings() -> Settings:
    """Load settings from environment."""
    return Settings()

