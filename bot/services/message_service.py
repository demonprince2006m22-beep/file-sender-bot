"""Service for rendering customizable messages with safe placeholder replacement."""

import logging
import string
from typing import Any, Dict, Optional

from bot.config import DEFAULT_MESSAGES
from bot.database.repository import Repository

logger = logging.getLogger(__name__)


class _SafeFormatter(string.Formatter):
    """String formatter that leaves unknown keys intact instead of throwing KeyError."""

    def __init__(self, default: str = ""):
        self.default = default

    def get_value(self, key: Any, args: tuple, kwargs: dict) -> Any:
        if isinstance(key, str):
            if key in kwargs:
                return kwargs[key]
            # Return placeholder verbatim if not provided
            return f"{{{key}}}"
        return super().get_value(key, args, kwargs)


_formatter = _SafeFormatter()


class MessageService:
    """Retrieves and formats user-facing and admin bot messages."""

    def __init__(self, repo: Repository):
        self.repo = repo

    async def get_raw_template(self, key: str) -> str:
        """Fetch template from database or fallback to default."""
        stored = await self.repo.get_setting(key)
        if stored:
            return stored
        return DEFAULT_MESSAGES.get(key, "")

    async def render(self, template_key: str, **placeholders: Any) -> str:
        """Fetch template by key and interpolate placeholders safely."""
        template = await self.get_raw_template(template_key)
        return self.format_text(template, **placeholders)

    @staticmethod
    def format_text(template: str, **placeholders: Any) -> str:
        """Safely format a template string with given placeholders."""
        # Sanitize placeholders: convert None to empty string
        safe_kwargs: Dict[str, Any] = {
            k: ("" if v is None else str(v)) for k, v in placeholders.items()
        }
        try:
            return _formatter.format(template, **safe_kwargs)
        except Exception as e:
            logger.warning("Error formatting message template: %s. Using raw template.", e)
            return template

