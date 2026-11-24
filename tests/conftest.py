"""Pytest configuration and shared fixtures."""

import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator
import pytest
import pytest_asyncio

from bot.config import Settings
from bot.database.db import Database
from bot.database.repository import Repository
from bot.services import (
    AuditService,
    AutoDeleteService,
    ChannelService,
    FileService,
    MessageService,
)


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated test settings with temporary SQLite path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db_path = Path(tf.name)

    settings = Settings(
        BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
        OWNER_ID=10001,
        ADMIN_IDS=[10002, 10003],
        STORAGE_CHANNEL_ID=-1009999999999,
        DATABASE_PATH=temp_db_path,
        DEFAULT_EXPIRY_HOURS=0,
        DEFAULT_DELIVERY_LIMIT=0,
        FORCE_SUB_ENABLED=True,
    )
    yield settings

    # Clean up temp db
    if temp_db_path.exists():
        try:
            temp_db_path.unlink()
        except Exception:
            pass


@pytest_asyncio.fixture
async def db(test_settings: Settings) -> AsyncGenerator[Database, None]:
    """Initialize a fresh temporary test database."""
    database = Database(test_settings.DATABASE_PATH)
    await database.init_db(test_settings)
    yield database


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Provide repository connected to test database."""
    return Repository(db)


@pytest_asyncio.fixture
async def file_service(repo: Repository) -> FileService:
    """Provide FileService instance."""
    return FileService(repo)


@pytest_asyncio.fixture
async def channel_service(repo: Repository) -> ChannelService:
    """Provide ChannelService instance."""
    return ChannelService(repo)


@pytest_asyncio.fixture
async def message_service(repo: Repository) -> MessageService:
    """Provide MessageService instance."""
    return MessageService(repo)


@pytest_asyncio.fixture
async def audit_service(repo: Repository) -> AuditService:
    """Provide AuditService instance."""
    return AuditService(repo)


@pytest_asyncio.fixture
async def auto_delete_service(repo: Repository) -> AutoDeleteService:
    """Provide AutoDeleteService instance."""
    return AutoDeleteService(repo)


