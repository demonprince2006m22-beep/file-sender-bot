"""Unit tests for channel subscription checks and outcomes."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberMember, ChatMemberLeft, ChatMemberRestricted

from bot.database.models import RequiredChannel
from bot.database.repository import Repository
from bot.services import ChannelService


@pytest.mark.asyncio
async def test_no_required_channels(
    repo: Repository, channel_service: ChannelService
):
    """When no channels are configured, user passes verification automatically."""
    bot_mock = AsyncMock(spec=Bot)
    all_joined, missing = await channel_service.check_user_membership(
        bot=bot_mock, user_id=12345
    )
    assert all_joined is True
    assert missing == []
    bot_mock.get_chat_member.assert_not_called()


@pytest.mark.asyncio
async def test_all_channels_joined(
    repo: Repository, channel_service: ChannelService
):
    """When user is a member of all enabled channels, verification passes."""
    await repo.add_required_channel(
        RequiredChannel(
            channel_id=-1001111111111,
            display_name="News Channel",
            join_url="https://t.me/news",
            is_enabled=True,
            added_by=10001,
        )
    )
    await repo.add_required_channel(
        RequiredChannel(
            channel_id=-1002222222222,
            display_name="Updates Channel",
            join_url="https://t.me/updates",
            is_enabled=True,
            added_by=10001,
        )
    )

    bot_mock = AsyncMock(spec=Bot)
    # Mock get_chat_member returning active member status
    member_obj = MagicMock(spec=ChatMemberMember)
    member_obj.status = ChatMemberStatus.MEMBER
    bot_mock.get_chat_member.return_value = member_obj

    all_joined, missing = await channel_service.check_user_membership(
        bot=bot_mock, user_id=55555
    )
    assert all_joined is True
    assert len(missing) == 0
    assert bot_mock.get_chat_member.call_count == 2


@pytest.mark.asyncio
async def test_missing_required_channel(
    repo: Repository, channel_service: ChannelService
):
    """When user has left or not joined one channel, verification fails and reports missing channel."""
    ch1 = await repo.add_required_channel(
        RequiredChannel(
            channel_id=-1001111111111,
            display_name="Channel 1",
            join_url="https://t.me/ch1",
            is_enabled=True,
            added_by=10001,
        )
    )
    ch2 = await repo.add_required_channel(
        RequiredChannel(
            channel_id=-1002222222222,
            display_name="Channel 2",
            join_url="https://t.me/ch2",
            is_enabled=True,
            added_by=10001,
        )
    )

    bot_mock = AsyncMock(spec=Bot)

    # First channel is member, second channel is left
    async def mock_get_chat_member(chat_id: int, user_id: int):
        if chat_id == ch1.channel_id:
            m = MagicMock(spec=ChatMemberMember)
            m.status = ChatMemberStatus.MEMBER
            return m
        else:
            m = MagicMock(spec=ChatMemberLeft)
            m.status = ChatMemberStatus.LEFT
            return m

    bot_mock.get_chat_member.side_effect = mock_get_chat_member

    all_joined, missing = await channel_service.check_user_membership(
        bot=bot_mock, user_id=55555
    )
    assert all_joined is False
    assert len(missing) == 1
    assert missing[0].channel_id == ch2.channel_id
    assert missing[0].display_name == "Channel 2"


@pytest.mark.asyncio
async def test_disabled_channel_is_skipped(
    repo: Repository, channel_service: ChannelService
):
    """Disabled channels must not block users even if not joined."""
    # Add disabled channel
    await repo.add_required_channel(
        RequiredChannel(
            channel_id=-1003333333333,
            display_name="Disabled Channel",
            join_url="https://t.me/disabled",
            is_enabled=False,
            added_by=10001,
        )
    )

    bot_mock = AsyncMock(spec=Bot)
    all_joined, missing = await channel_service.check_user_membership(
        bot=bot_mock, user_id=55555
    )
    assert all_joined is True
    assert len(missing) == 0
    bot_mock.get_chat_member.assert_not_called()


@pytest.mark.asyncio
async def test_force_sub_disabled_globally(
    repo: Repository, channel_service: ChannelService
):
    """When force_sub_enabled setting is false, membership checks are bypassed."""
    await repo.add_required_channel(
        RequiredChannel(
            channel_id=-1001111111111,
            display_name="Channel 1",
            join_url="https://t.me/ch1",
            is_enabled=True,
            added_by=10001,
        )
    )

    # Disable force subscription globally
    await repo.set_setting("force_sub_enabled", "false")

    bot_mock = AsyncMock(spec=Bot)
    all_joined, missing = await channel_service.check_user_membership(
        bot=bot_mock, user_id=55555
    )
    assert all_joined is True
    assert missing == []
    bot_mock.get_chat_member.assert_not_called()

