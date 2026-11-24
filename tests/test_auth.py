"""Unit tests for admin and owner authorization."""

import pytest
from unittest.mock import MagicMock
from aiogram.types import CallbackQuery, Message, User

from bot.database.repository import Repository
from bot.middlewares.auth_middleware import IsAdminFilter, IsOwnerFilter


@pytest.mark.asyncio
async def test_initial_admins_seeded(repo: Repository):
    """Test that owner and configured admins are properly seeded."""
    assert await repo.is_owner(10001) is True
    assert await repo.is_admin(10001) is True

    # Seeded admins
    assert await repo.is_admin(10002) is True
    assert await repo.is_admin(10003) is True
    assert await repo.is_owner(10002) is False

    # Random unauthorized user
    assert await repo.is_admin(99999) is False
    assert await repo.is_owner(99999) is False


@pytest.mark.asyncio
async def test_dynamic_add_and_remove_admin(repo: Repository):
    """Test owner adding and revoking new admins."""
    new_admin_id = 20005
    assert await repo.is_admin(new_admin_id) is False

    # Add admin
    added = await repo.add_admin(new_admin_id, role="admin", added_by=10001)
    assert added is True
    assert await repo.is_admin(new_admin_id) is True
    assert await repo.is_owner(new_admin_id) is False

    # Revoke admin
    removed = await repo.remove_admin(new_admin_id)
    assert removed is True
    assert await repo.is_admin(new_admin_id) is False


@pytest.mark.asyncio
async def test_owner_cannot_be_revoked(repo: Repository):
    """Ensure bot owner cannot be revoked from admins table."""
    owner_id = 10001
    assert await repo.is_owner(owner_id) is True

    # Attempt to remove owner
    await repo.remove_admin(owner_id)
    # Owner must still be owner and admin
    assert await repo.is_owner(owner_id) is True
    assert await repo.is_admin(owner_id) is True


@pytest.mark.asyncio
async def test_admin_filter(repo: Repository):
    """Test aiogram IsAdminFilter behavior."""
    filter_obj = IsAdminFilter()

    # Admin message
    admin_msg = MagicMock(spec=Message)
    admin_msg.from_user = MagicMock(spec=User)
    admin_msg.from_user.id = 10002
    assert await filter_obj(admin_msg, repo=repo) is True

    # Non-admin message
    stranger_msg = MagicMock(spec=Message)
    stranger_msg.from_user = MagicMock(spec=User)
    stranger_msg.from_user.id = 88888
    assert await filter_obj(stranger_msg, repo=repo) is False

    # Non-admin callback query
    stranger_cb = MagicMock(spec=CallbackQuery)
    stranger_cb.from_user = MagicMock(spec=User)
    stranger_cb.from_user.id = 88888
    assert await filter_obj(stranger_cb, repo=repo) is False


@pytest.mark.asyncio
async def test_owner_filter(repo: Repository):
    """Test aiogram IsOwnerFilter behavior."""
    filter_obj = IsOwnerFilter()

    # Owner
    owner_msg = MagicMock(spec=Message)
    owner_msg.from_user = MagicMock(spec=User)
    owner_msg.from_user.id = 10001
    assert await filter_obj(owner_msg, repo=repo) is True

    # Regular admin should be rejected by OwnerFilter
    admin_msg = MagicMock(spec=Message)
    admin_msg.from_user = MagicMock(spec=User)
    admin_msg.from_user.id = 10002
    assert await filter_obj(admin_msg, repo=repo) is False

