"""Authentication and authorization filters and middlewares."""

import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.repository import Repository

logger = logging.getLogger(__name__)


class IsAdminFilter(BaseFilter):
    """Filter that checks if the sender's Telegram numeric ID is an authorized admin."""

    async def __call__(
        self, event: TelegramObject, repo: Repository
    ) -> bool:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if not user_id:
            return False

        is_adm = await repo.is_admin(user_id)
        if not is_adm:
            logger.debug("Filter evaluated False for non-admin user %s", user_id)
        return is_adm


class IsOwnerFilter(BaseFilter):
    """Filter that strictly restricts actions to the bot Owner."""

    async def __call__(
        self, event: TelegramObject, repo: Repository
    ) -> bool:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if not user_id:
            return False

        return await repo.is_owner(user_id)

