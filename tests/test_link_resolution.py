"""Unit tests for file link tokens and resolution."""

import pytest
from bot.database.models import FileRecord
from bot.database.repository import Repository
from bot.services import generate_secure_token


def test_token_properties():
    """Verify generated tokens are cryptographically unguessable and URL safe."""
    tokens = {generate_secure_token() for _ in range(100)}
    assert len(tokens) == 100
    for tok in tokens:
        assert len(tok) >= 20
        # Check URL safety
        assert "/" not in tok
        assert "+" not in tok
        assert "=" not in tok


@pytest.mark.asyncio
async def test_file_creation_and_token_lookup(repo: Repository):
    """Test storing file record and retrieving by token."""
    token = generate_secure_token()
    file_record = FileRecord(
        link_token=token,
        file_id="BQACAgIAAxkBAAI...",
        file_unique_id="AgADxx...",
        file_name="Report_2026.pdf",
        media_type="document",
        file_size=1048576,
        mime_type="application/pdf",
        storage_channel_id=-1009999999999,
        storage_message_id=42,
        status="active",
        created_by=10001,
    )

    created = await repo.create_file(file_record)
    assert created.id is not None

    # Retrieve by token
    fetched = await repo.get_file_by_token(token)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.file_name == "Report_2026.pdf"
    assert fetched.storage_channel_id == -1009999999999
    assert fetched.storage_message_id == 42
    assert fetched.is_active is True

    # Non-existent token
    missing = await repo.get_file_by_token("unknown_token_123")
    assert missing is None


@pytest.mark.asyncio
async def test_token_regeneration(repo: Repository):
    """Test regenerating a token for an existing file invalidates old token."""
    old_token = generate_secure_token()
    file = await repo.create_file(
        FileRecord(
            link_token=old_token,
            file_id="FILE_123",
            file_unique_id="UNIQ_123",
            file_name="Secret.mp4",
            media_type="video",
            storage_channel_id=-1009999999999,
            storage_message_id=10,
            status="active",
            created_by=10001,
        )
    )

    new_token = generate_secure_token()
    assert new_token != old_token

    # Regenerate
    success = await repo.update_file_token(file.id, new_token)
    assert success is True

    # Old token lookup should now return None
    assert await repo.get_file_by_token(old_token) is None

    # New token lookup should succeed
    updated = await repo.get_file_by_token(new_token)
    assert updated is not None
    assert updated.id == file.id


@pytest.mark.asyncio
async def test_database_backup(db, test_settings):
    """Test online backup generation."""
    import tempfile
    from pathlib import Path

    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    backup_path = Path(tf.name)
    tf.close()

    try:
        saved = await db.backup(backup_path)
        assert saved.exists()
        assert saved.stat().st_size > 0
    finally:
        if backup_path.exists():
            backup_path.unlink()
