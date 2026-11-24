"""Unit tests for file auto-delete scheduling, persistence, and worker execution."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram import Bot
from aiogram.types import Message

from bot.database.models import FileRecord
from bot.database.repository import Repository
from bot.handlers.user import handle_delivery_auto_delete
from bot.services import AutoDeleteService, MessageService, format_delete_time


@pytest.mark.asyncio
async def test_format_delete_time():
    """Verify human-readable format for various minute intervals."""
    assert format_delete_time(0) == "immediately"
    assert format_delete_time(1) == "1 minute"
    assert format_delete_time(5) == "5 minutes"
    assert format_delete_time(60) == "1 hour"
    assert format_delete_time(120) == "2 hours"
    assert format_delete_time(90) == "1h 30m"


@pytest.mark.asyncio
async def test_update_file_auto_delete(repo: Repository):
    """Test updating file-specific auto-delete configuration in database."""
    file = await repo.create_file(
        FileRecord(
            link_token="autodel_token_1",
            file_id="FILE_AD_1",
            file_unique_id="UNIQ_AD_1",
            file_name="Movie.mp4",
            media_type="video",
            storage_channel_id=-1001234567890,
            storage_message_id=10,
            status="active",
            created_by=10001,
        )
    )

    # Initial state is None (uses global default)
    assert file.auto_delete_minutes is None

    # Set custom 15 minutes
    updated = await repo.update_file_auto_delete(file.id, 15)
    assert updated is True

    refreshed = await repo.get_file_by_id(file.id)
    assert refreshed.auto_delete_minutes == 15

    # Set 0 (explicitly never delete)
    await repo.update_file_auto_delete(file.id, 0)
    refreshed2 = await repo.get_file_by_id(file.id)
    assert refreshed2.auto_delete_minutes == 0

    # Revert to None (global default)
    await repo.update_file_auto_delete(file.id, None)
    refreshed3 = await repo.get_file_by_id(file.id)
    assert refreshed3.auto_delete_minutes is None


@pytest.mark.asyncio
async def test_pending_deletion_db_operations(repo: Repository):
    """Test adding, fetching due, and removing pending deletions."""
    now = datetime.now(timezone.utc)
    due_time = now - timedelta(seconds=10)
    future_time = now + timedelta(hours=1)

    # Add overdue item
    id1 = await repo.add_pending_deletion(chat_id=111, message_id=222, delete_at=due_time)
    # Add future item
    id2 = await repo.add_pending_deletion(chat_id=333, message_id=444, delete_at=future_time)

    # Fetch due deletions
    due = await repo.get_due_deletions(now)
    assert len(due) == 1
    assert due[0] == (id1, 111, 222)

    # Delete overdue item
    removed = await repo.delete_pending_deletion(id1)
    assert removed is True

    # No due items remaining
    due_after = await repo.get_due_deletions(now)
    assert len(due_after) == 0

    # Clean up future item
    await repo.delete_pending_deletion(id2)


@pytest.mark.asyncio
async def test_auto_delete_worker_execution(repo: Repository, auto_delete_service: AutoDeleteService):
    """Test background worker polling and deleting due messages."""
    bot_mock = AsyncMock(spec=Bot)
    bot_mock.delete_message = AsyncMock()

    past_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    del_id = await repo.add_pending_deletion(chat_id=999, message_id=888, delete_at=past_time)

    # Start worker briefly
    worker = auto_delete_service.start_worker(bot_mock)
    await asyncio.sleep(0.2)  # Give worker a moment to process the due deletion
    await auto_delete_service.stop_worker()

    # Bot delete_message should have been called
    bot_mock.delete_message.assert_called_with(chat_id=999, message_id=888)

    # Record should have been removed from pending_deletions
    remaining = await repo.get_due_deletions()
    assert len(remaining) == 0


@pytest.mark.asyncio
async def test_handle_delivery_auto_delete_file_override(
    repo: Repository,
    auto_delete_service: AutoDeleteService,
    message_service: MessageService,
):
    """Test handle_delivery_auto_delete triggers scheduling when file has custom auto-delete."""
    bot_mock = AsyncMock(spec=Bot)
    warn_mock = MagicMock(spec=Message)
    warn_mock.message_id = 555
    bot_mock.send_message.return_value = warn_mock

    file = FileRecord(
        id=1,
        file_name="Confidential.pdf",
        auto_delete_minutes=10,  # 10 minutes custom
    )

    file_msg = MagicMock(spec=Message)
    file_msg.message_id = 777

    notice_msg = MagicMock(spec=Message)
    notice_msg.message_id = 888

    await handle_delivery_auto_delete(
        bot=bot_mock,
        repo=repo,
        auto_delete_service=auto_delete_service,
        message_service=message_service,
        user_id=12345,
        file=file,
        file_message=file_msg,
        notice_message=notice_msg,
    )

    # Verification notice was sent
    bot_mock.send_message.assert_called_once()

    # Check pending deletions were scheduled in DB
    async with repo.db.connection() as conn:
        cursor = await conn.execute("SELECT chat_id, message_id FROM pending_deletions")
        rows = await cursor.fetchall()

    # Expect 3 messages scheduled (file_msg, warn_msg, notice_msg)
    scheduled_msg_ids = {r["message_id"] for r in rows}
    assert 777 in scheduled_msg_ids
    assert 555 in scheduled_msg_ids
    assert 888 in scheduled_msg_ids


@pytest.mark.asyncio
async def test_handle_delivery_auto_delete_disabled(
    repo: Repository,
    auto_delete_service: AutoDeleteService,
    message_service: MessageService,
):
    """Test handle_delivery_auto_delete does nothing when auto-delete is disabled."""
    bot_mock = AsyncMock(spec=Bot)

    file = FileRecord(
        id=2,
        file_name="Public.mp4",
        auto_delete_minutes=0,  # Explicitly disabled
    )

    file_msg = MagicMock(spec=Message)
    file_msg.message_id = 100

    await handle_delivery_auto_delete(
        bot=bot_mock,
        repo=repo,
        auto_delete_service=auto_delete_service,
        message_service=message_service,
        user_id=12345,
        file=file,
        file_message=file_msg,
    )

    # Send message should NOT be called
    bot_mock.send_message.assert_not_called()

