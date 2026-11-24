"""Main entry point for File Sender Bot."""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault

from bot.config import Settings, get_settings
from bot.database.db import Database
from bot.database.repository import Repository
from bot.handlers.admin_channels import router as admin_channels_router
from bot.handlers.admin_files import router as admin_files_router
from bot.handlers.admin_manage import router as admin_manage_router
from bot.handlers.admin_messages import router as admin_messages_router
from bot.handlers.admin_panel import router as admin_panel_router
from bot.handlers.admin_settings import router as admin_settings_router
from bot.handlers.admin_storage import router as admin_storage_router
from bot.handlers.admin_upload import router as admin_upload_router
from bot.handlers.user import router as user_router
from bot.middlewares.idempotency import CallbackDebounceMiddleware
from bot.services import (
    AuditService,
    AutoDeleteService,
    ChannelService,
    FileService,
    MessageService,
)

logger = logging.getLogger("file_sender_bot")


async def setup_bot_commands(bot: Bot) -> None:
    """Register public commands with Telegram."""
    commands = [
        BotCommand(command="start", description="Start bot / retrieve file"),
        BotCommand(command="help", description="Show usage guide"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        logger.warning("Could not set bot commands: %s", e)


async def main() -> None:
    """Initialize resources and start polling."""
    # 1. Load settings
    settings: Settings = get_settings()

    # 2. Configure logging
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Starting Telegram File Sender Bot...")

    # 3. Initialize database
    db = Database(settings.DATABASE_PATH)
    await db.init_db(settings)
    repo = Repository(db)

    # 4. Initialize services
    file_service = FileService(repo)
    channel_service = ChannelService(repo)
    message_service = MessageService(repo)
    audit_service = AuditService(repo)
    auto_delete_service = AutoDeleteService(repo)

    # 5. Initialize Telegram Bot & Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # 6. Register Middlewares
    dp.callback_query.middleware(CallbackDebounceMiddleware(debounce_seconds=1.0))

    # Pass dependencies to all handlers via workflow_data
    dp["repo"] = repo
    dp["file_service"] = file_service
    dp["channel_service"] = channel_service
    dp["message_service"] = message_service
    dp["audit_service"] = audit_service
    dp["auto_delete_service"] = auto_delete_service
    dp["settings"] = settings

    # 7. Register routers (Admin routers before user router so admin commands/uploads take precedence)
    dp.include_router(admin_panel_router)
    dp.include_router(admin_upload_router)
    dp.include_router(admin_channels_router)
    dp.include_router(admin_storage_router)
    dp.include_router(admin_files_router)
    dp.include_router(admin_messages_router)
    dp.include_router(admin_settings_router)
    dp.include_router(admin_manage_router)
    dp.include_router(user_router)

    # 8. Start polling
    await setup_bot_commands(bot)
    logger.info("Bot commands configured. Starting polling...")

    try:
        # Drop pending updates on startup to prevent stale processing
        await bot.delete_webhook(drop_pending_updates=True)
        auto_delete_service.start_worker(bot)
        await dp.start_polling(bot)
    finally:
        logger.info("Shutting down bot session...")
        await auto_delete_service.stop_worker()
        await bot.session.close()
        logger.info("Bot successfully stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process interrupted by user. Exiting.")
        sys.exit(0)

