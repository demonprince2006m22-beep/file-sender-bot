"""Unit tests for file delivery eligibility, link states, and limits."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from aiogram import Bot
from aiogram.types import Message

from bot.database.models import FileRecord
from bot.database.repository import Repository
from bot.services import FileAccessStatus, FileService, generate_secure_token


@pytest.mark.asyncio
async def test_access_active_file(
    repo: Repository, file_service: FileService
):
    """An active file within validity period should return ALLOWED."""
    token = generate_secure_token()
    file = await repo.create_file(
        FileRecord(
            link_token=token,
            file_id="FILE_OK",
            file_unique_id="UNIQ_OK",
            file_name="Video.mp4",
            media_type="video",
            storage_channel_id=-1009999999999,
            storage_message_id=1,
            status="active",
            created_by=10001,
        )
    )

    status, fetched = await file_service.evaluate_access(token, user_id=777)
    assert status == FileAccessStatus.ALLOWED
    assert fetched is not None
    assert fetched.id == file.id


@pytest.mark.asyncio
async def test_access_disabled_file(
    repo: Repository, file_service: FileService
):
    """A disabled file returns DISABLED."""
    token = generate_secure_token()
    await repo.create_file(
        FileRecord(
            link_token=token,
            file_id="FILE_DIS",
            file_unique_id="UNIQ_DIS",
            status="disabled",
            storage_channel_id=-1009999999999,
            storage_message_id=2,
            created_by=10001,
        )
    )

    status, fetched = await file_service.evaluate_access(token, user_id=777)
    assert status == FileAccessStatus.DISABLED
    assert fetched is not None


@pytest.mark.asyncio
async def test_access_deleted_file(
    repo: Repository, file_service: FileService
):
    """A deleted file returns DELETED."""
    token = generate_secure_token()
    await repo.create_file(
        FileRecord(
            link_token=token,
            file_id="FILE_DEL",
            file_unique_id="UNIQ_DEL",
            status="deleted",
            storage_channel_id=-1009999999999,
            storage_message_id=3,
            created_by=10001,
        )
    )

    status, fetched = await file_service.evaluate_access(token, user_id=777)
    assert status == FileAccessStatus.DELETED


@pytest.mark.asyncio
async def test_access_expired_file(
    repo: Repository, file_service: FileService
):
    """An expired file returns EXPIRED."""
    token = generate_secure_token()
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)

    await repo.create_file(
        FileRecord(
            link_token=token,
            file_id="FILE_EXP",
            file_unique_id="UNIQ_EXP",
            status="active",
            expires_at=past_time,
            storage_channel_id=-1009999999999,
            storage_message_id=4,
            created_by=10001,
        )
    )

    status, fetched = await file_service.evaluate_access(token, user_id=777)
    assert status == FileAccessStatus.EXPIRED


@pytest.mark.asyncio
async def test_per_user_delivery_limit(
    repo: Repository, file_service: FileService
):
    """Test enforcing per-user download limits."""
    token = generate_secure_token()
    file = await repo.create_file(
        FileRecord(
            link_token=token,
            file_id="FILE_LMT",
            file_unique_id="UNIQ_LMT",
            status="active",
            delivery_limit=2,  # Max 2 deliveries per user
            storage_channel_id=-1009999999999,
            storage_message_id=5,
            created_by=10001,
        )
    )

    user1 = 11111
    user2 = 22222

    # User 1 first delivery
    status, _ = await file_service.evaluate_access(token, user_id=user1)
    assert status == FileAccessStatus.ALLOWED
    await repo.record_delivery(file.id, user1)

    # User 1 second delivery
    status, _ = await file_service.evaluate_access(token, user_id=user1)
    assert status == FileAccessStatus.ALLOWED
    await repo.record_delivery(file.id, user1)

    # User 1 third delivery -> LIMIT REACHED
    status, _ = await file_service.evaluate_access(token, user_id=user1)
    assert status == FileAccessStatus.LIMIT_REACHED

    # User 2 is independent and can still download
    status_u2, _ = await file_service.evaluate_access(token, user_id=user2)
    assert status_u2 == FileAccessStatus.ALLOWED


@pytest.mark.asyncio
async def test_deliver_file_execution(
    repo: Repository, file_service: FileService
):
    """Test delivery execution copies message and records audit."""
    token = generate_secure_token()
    file = await repo.create_file(
        FileRecord(
            link_token=token,
            file_id="FILE_SEND",
            file_unique_id="UNIQ_SEND",
            file_name="Tutorial.mp4",
            media_type="video",
            storage_channel_id=-1009999999999,
            storage_message_id=99,
            status="active",
            created_by=10001,
        )
    )

    bot_mock = AsyncMock(spec=Bot)
    msg_mock = AsyncMock(spec=Message)
    bot_mock.copy_message.return_value = msg_mock

    user_id = 99901
    await file_service.deliver_file_to_user(bot_mock, user_id, file)

    # Check copy_message call parameters
    bot_mock.copy_message.assert_called_once_with(
        chat_id=user_id,
        from_chat_id=-1009999999999,
        message_id=99,
    )

    # Check deliveries record
    count = await repo.get_user_delivery_count(file.id, user_id)
    assert count == 1

    # Check file delivery count increment
    refreshed = await repo.get_file_by_id(file.id)
    assert refreshed.delivery_count == 1


@pytest.mark.asyncio
async def test_deliver_file_with_caption(
    repo: Repository, file_service: FileService
):
    """File delivery supports passing custom caption attached directly to the message."""
    from bot.handlers.user import build_delivery_caption

    file = await repo.create_file(
        FileRecord(
            link_token="TOKEN_CAPTION_1",
            file_id="FILE_CAPTION",
            file_unique_id="UNIQ_CAPTION",
            file_name="Video.mp4",
            media_type="video",
            caption="Original File Description",
            storage_channel_id=-1009999999999,
            storage_message_id=101,
            status="active",
            created_by=10001,
        )
    )

    bot_mock = AsyncMock(spec=Bot)
    msg_mock = AsyncMock(spec=Message)
    bot_mock.copy_message.return_value = msg_mock

    user_id = 99902
    success_text = "Here is your file, Alice!"
    caption = build_delivery_caption(file.caption, success_text)
    assert "Original File Description" in caption
    assert "Here is your file, Alice!" in caption

    await file_service.deliver_file_to_user(bot_mock, user_id, file, caption=caption)

    # Check copy_message received caption keyword argument
    bot_mock.copy_message.assert_called_once_with(
        chat_id=user_id,
        from_chat_id=-1009999999999,
        message_id=101,
        caption=caption,
    )


def test_build_delivery_caption_logic():
    """Verify build_delivery_caption handles empty captions and length limits."""
    from bot.handlers.user import build_delivery_caption

    # Empty file caption
    assert build_delivery_caption(None, "Success message") == "Success message"
    assert build_delivery_caption("", "Success message") == "Success message"

    # Both present
    combined = build_delivery_caption("Title", "Body")
    assert combined == "Title\n\nBody"

    # Excessively long caption truncated safely
    long_caption = "A" * 1500
    res = build_delivery_caption(long_caption, "Short success")
    assert len(res) <= 1024
    assert res.endswith("Short success")


