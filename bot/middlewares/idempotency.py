"""Idempotency and anti-flood debounce middleware."""

import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject


class CallbackDebounceMiddleware(BaseMiddleware):
    """
    Prevents duplicate concurrent callback clicks from the same user on the same callback data
    within a short debounce window (e.g. 1.0s).
    """

    def __init__(self, debounce_seconds: float = 1.0):
        super().__init__()
        self.debounce_seconds = debounce_seconds
        self._last_clicks: Dict[str, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.from_user and event.data:
            key = f"{event.from_user.id}:{event.data}"
            now = time.monotonic()
            last_time = self._last_clicks.get(key, 0.0)

            if now - last_time < self.debounce_seconds:
                # Silently acknowledge duplicate click
                await event.answer("⏳ Processing, please wait...")
                return None

            self._last_clicks[key] = now

            # Clean up old keys periodically
            if len(self._last_clicks) > 5000:
                threshold = now - 60.0
                self._last_clicks = {
                    k: t for k, t in self._last_clicks.items() if t > threshold
                }

        return await handler(event, data)

