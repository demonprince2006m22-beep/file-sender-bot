"""Unit tests for template placeholders and rendering."""

import pytest
from bot.config import DEFAULT_MESSAGES
from bot.database.repository import Repository
from bot.services import MessageService


@pytest.mark.asyncio
async def test_template_rendering_placeholders(
    message_service: MessageService,
):
    """Test successful substitution of placeholders."""
    rendered = await message_service.render(
        "msg_success",
        first_name="Alex",
        file_name="Document.pdf",
        file_size="5.2 MB",
    )
    assert "Alex" in rendered
    assert "Document.pdf" in rendered
    assert "5.2 MB" in rendered


@pytest.mark.asyncio
async def test_safe_unknown_placeholders(
    message_service: MessageService,
):
    """Unknown placeholders should not raise errors and be preserved safely."""
    custom_text = "Hello {first_name}, here is your {non_existent_key} code."
    formatted = message_service.format_text(custom_text, first_name="Sam")
    assert formatted == "Hello Sam, here is your {non_existent_key} code."


@pytest.mark.asyncio
async def test_custom_template_override_and_reset(
    repo: Repository, message_service: MessageService
):
    """Test overriding a template in database and reading it."""
    key = "msg_welcome"
    custom_msg = "Custom Welcome for {first_name}!"

    # Update in settings
    await repo.set_setting(key, custom_msg)
    rendered = await message_service.render(key, first_name="Chris")
    assert rendered == "Custom Welcome for Chris!"

    # Reset in settings
    default = DEFAULT_MESSAGES[key]
    await repo.set_setting(key, default)
    restored = await message_service.render(key, first_name="Chris")
    assert "Welcome to File Sender Bot!" in restored

