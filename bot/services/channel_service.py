"""Service for managing required subscription channels and permission verification."""

import logging
from typing import List, Optional, Tuple

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot.database.models import RequiredChannel
from bot.database.repository import Repository

logger = logging.getLogger(__name__)

ACTIVE_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


class ChannelService:
    """Handles channel membership checks and channel access verification."""

    def __init__(self, repo: Repository):
        self.repo = repo

    async def check_user_membership(
        self, bot: Bot, user_id: int
    ) -> Tuple[bool, List[RequiredChannel]]:
        """
        Check if user has joined all active required channels.
        Returns: (all_joined: bool, missing_channels: List[RequiredChannel])
        """
        # Check if force subscription is enabled
        force_sub_enabled = await self.repo.get_setting("force_sub_enabled", "true")
        if force_sub_enabled.lower() not in ("true", "1", "yes"):
            return True, []

        channels = await self.repo.list_required_channels(only_enabled=True)
        if not channels:
            return True, []

        missing_channels: List[RequiredChannel] = []

        for ch in channels:
            is_member = await self.is_user_in_channel(bot, ch.channel_id, user_id)
            if not is_member:
                missing_channels.append(ch)

        return len(missing_channels) == 0, missing_channels

    async def is_user_in_channel(self, bot: Bot, channel_id: int, user_id: int) -> bool:
        """Query Telegram API for user status in a specific channel."""
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)

            if member.status in ACTIVE_MEMBER_STATUSES:
                return True

            if member.status == ChatMemberStatus.RESTRICTED:
                # In some groups/channels restricted users are still members
                return getattr(member, "is_member", False)

            return False
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            logger.warning(
                "Failed to check membership for user %s in channel %s: %s",
                user_id,
                channel_id,
                e,
            )
            # If the user is simply not found in chat, Telegram returns 'user not found'
            return False
        except Exception as e:
            logger.error(
                "Unexpected error checking channel %s for user %s: %s",
                channel_id,
                user_id,
                e,
            )
            return False

    async def verify_channel_access(
        self, bot: Bot, channel_id: int
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Verify that the bot has access to a required channel and can inspect members.
        Returns: (success: bool, status_message: str, channel_title: Optional[str])
        """
        try:
            chat = await bot.get_chat(chat_id=channel_id)
            bot_member = await bot.get_chat_member(
                chat_id=channel_id, user_id=bot.id
            )

            if bot_member.status not in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
            ):
                return (
                    False,
                    f"Bot is in channel '{chat.title}' but is NOT an administrator. It needs admin status to reliably verify user memberships.",
                    chat.title,
                )

            return (
                True,
                f"✅ Verified! Bot is administrator in '{chat.title}'.",
                chat.title,
            )
        except TelegramForbiddenError:
            return (
                False,
                "❌ Bot was removed from the channel or has not been added yet.",
                None,
            )
        except TelegramBadRequest as e:
            return (
                False,
                f"❌ Telegram error accessing channel ({e.message}). Ensure channel ID is correct (usually starts with -100) and the bot is added.",
                None,
            )
        except Exception as e:
            return False, f"❌ Unexpected error: {str(e)}", None

    async def verify_storage_channel(
        self, bot: Bot, channel_id: int
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Verify that the private storage channel is accessible and the bot can post messages.
        Returns: (success: bool, status_message: str, channel_title: Optional[str])
        """
        try:
            chat = await bot.get_chat(chat_id=channel_id)
            bot_member = await bot.get_chat_member(
                chat_id=channel_id, user_id=bot.id
            )

            if bot_member.status not in (
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
            ):
                return (
                    False,
                    f"Bot is in '{chat.title}' but is not an administrator with 'Post Messages' privilege.",
                    chat.title,
                )

            # Check post messages permission if administrator
            can_post = getattr(bot_member, "can_post_messages", True)
            if not can_post and bot_member.status != ChatMemberStatus.CREATOR:
                return (
                    False,
                    f"Bot is admin in '{chat.title}' but lacks 'Post Messages' permission.",
                    chat.title,
                )

            return (
                True,
                f"✅ Storage channel '{chat.title}' verified. Bot has full posting permissions.",
                chat.title,
            )
        except TelegramForbiddenError:
            return (
                False,
                "❌ Bot cannot access the storage channel. Add the bot to the channel as an Administrator.",
                None,
            )
        except TelegramBadRequest as e:
            return (
                False,
                f"❌ Telegram error ({e.message}). Ensure the storage channel ID starts with -100 and the bot is an admin.",
                None,
            )
        except Exception as e:
            return False, f"❌ Error verifying storage channel: {str(e)}", None

