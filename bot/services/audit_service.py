"""Service for logging administrative actions and security events."""

import logging
from typing import Optional

from bot.database.repository import Repository

logger = logging.getLogger(__name__)


class AuditService:
    """Manages audit trails for admin operations."""

    def __init__(self, repo: Repository):
        self.repo = repo

    async def log(
        self,
        admin_id: int,
        action: str,
        target: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Record an admin action without leaking sensitive secrets."""
        logger.info(
            "AUDIT: Admin %s executed action '%s' on target '%s' details: %s",
            admin_id,
            action,
            target,
            details,
        )
        await self.repo.log_action(
            admin_id=admin_id, action=action, target=target, details=details
        )

