"""Service for scheduling, managing, and executing automatic message deletions."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.database.repository import Repository

logger = logging.getLogger(__name__)


def format_delete_time(minutes: int) -> str:
    """Convert minutes to human-friendly text (e.g. '5 minutes', '1 hour', '2 hours')."""
    if minutes <= 0:
        return "immediately"
    if minutes == 1:
        return "1 minute"
    if minutes < 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    rem_min = minutes % 60
    if rem_min == 0:
        return "1 hour" if hours == 1 else f"{hours} hours"
    return f"{hours}h {rem_min}m"


class AutoDeleteService:
    """Schedules and processes auto-deletions of delivered files and notice messages."""

    def __init__(self, repo: Repository):
        self.repo = repo
        self._worker_task: Optional[asyncio.Task] = None
        self._stopping: bool = False

    async def schedule_deletion(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        delay_seconds: int,
    ) -> None:
        """Persist deletion schedule and spawn an in-memory deletion task for fast execution."""
        if delay_seconds <= 0:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.debug("Failed immediate delete of msg %s: %s", message_id, e)
            return

        delete_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        deletion_id = await self.repo.add_pending_deletion(chat_id, message_id, delete_at)

        # Spawn an async sleep task for fast handling
        asyncio.create_task(
            self._delayed_delete(bot, chat_id, message_id, delay_seconds, deletion_id)
        )

    async def _delayed_delete(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        delay_seconds: int,
        deletion_id: int,
    ) -> None:
        """Sleeps and deletes message, catching and logging any errors."""
        try:
            await asyncio.sleep(delay_seconds)
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.info(
                "Auto-deleted message %s in chat %s after %ss",
                message_id,
                chat_id,
                delay_seconds,
            )
        except TelegramBadRequest as e:
            logger.debug(
                "Could not delete message %s in chat %s (may have been deleted by user): %s",
                message_id,
                chat_id,
                e,
            )
        except Exception as e:
            logger.warning(
                "Error during auto-deletion of msg %s in chat %s: %s",
                message_id,
                chat_id,
                e,
            )
        finally:
            try:
                await self.repo.delete_pending_deletion(deletion_id)
            except Exception:
                pass

    def start_worker(self, bot: Bot) -> asyncio.Task:
        """Start the background poll loop to process any due or missed deletions across restarts."""
        self._stopping = False
        self._worker_task = asyncio.create_task(self._worker_loop(bot))
        return self._worker_task

    async def stop_worker(self) -> None:
        """Gracefully stop background loop."""
        self._stopping = True
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker_loop(self, bot: Bot) -> None:
        """Poll database for due deletions and execute them."""
        logger.info("Auto-delete background worker started.")
        while not self._stopping:
            try:
                due = await self.repo.get_due_deletions(datetime.now(timezone.utc))
                for del_id, chat_id, message_id in due:
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=message_id)
                        logger.info(
                            "Worker auto-deleted overdue message %s in chat %s",
                            message_id,
                            chat_id,
                        )
                    except TelegramBadRequest as e:
                        logger.debug(
                            "Worker: message %s already deleted or inaccessible: %s",
                            message_id,
                            e,
                        )
                    except Exception as e:
                        logger.warning("Worker: error deleting message %s: %s", message_id, e)
                    finally:
                        await self.repo.delete_pending_deletion(del_id)
            except Exception as e:
                logger.error("Error in auto-delete worker loop: %s", e)

            await asyncio.sleep(5)

