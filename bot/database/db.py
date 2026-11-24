"""Database connection and initialization module."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
import aiosqlite

from bot.config import Settings, DEFAULT_MESSAGES

logger = logging.getLogger(__name__)


class Database:
    """Manages SQLite database connections and lifecycle."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Async context manager that yields a configured aiosqlite connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys = ON;")
            await conn.execute("PRAGMA journal_mode = WAL;")
            yield conn

    async def init_db(self, settings: Settings) -> None:
        """Apply schema and seed initial settings and admins."""
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found at {schema_path}")

        schema_sql = schema_path.read_text(encoding="utf-8")

        async with self.connection() as conn:
            await conn.executescript(schema_sql)

            # Schema migrations for existing databases
            cursor = await conn.execute("PRAGMA table_info(files);")
            files_cols = [row["name"] for row in await cursor.fetchall()]
            if "auto_delete_minutes" not in files_cols:
                await conn.execute("ALTER TABLE files ADD COLUMN auto_delete_minutes INTEGER NULL;")

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_deletions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    delete_at TIMESTAMP NOT NULL
                );
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_delete_at ON pending_deletions(delete_at);"
            )

            # Seed owner into admins table
            await conn.execute(
                """
                INSERT INTO admins (telegram_id, role, added_by)
                VALUES (?, 'owner', ?)
                ON CONFLICT(telegram_id) DO UPDATE SET role = 'owner';
                """,
                (settings.OWNER_ID, settings.OWNER_ID),
            )

            # Seed initial admin IDs from config
            for admin_id in settings.ADMIN_IDS:
                if admin_id != settings.OWNER_ID:
                    await conn.execute(
                        """
                        INSERT INTO admins (telegram_id, role, added_by)
                        VALUES (?, 'admin', ?)
                        ON CONFLICT(telegram_id) DO NOTHING;
                        """,
                        (admin_id, settings.OWNER_ID),
                    )

            # Seed default storage channel if provided in env
            if settings.STORAGE_CHANNEL_ID:
                await conn.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES ('storage_channel_id', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value;
                    """,
                    (str(settings.STORAGE_CHANNEL_ID),),
                )

            # Seed behavior settings
            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('force_sub_enabled', ?)
                ON CONFLICT(key) DO NOTHING;
                """,
                (str(settings.FORCE_SUB_ENABLED).lower(),),
            )

            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('default_expiry_hours', ?)
                ON CONFLICT(key) DO NOTHING;
                """,
                (str(settings.DEFAULT_EXPIRY_HOURS),),
            )

            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('default_delivery_limit', ?)
                ON CONFLICT(key) DO NOTHING;
                """,
                (str(settings.DEFAULT_DELIVERY_LIMIT),),
            )

            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('auto_delete_minutes', ?)
                ON CONFLICT(key) DO NOTHING;
                """,
                (str(getattr(settings, "DEFAULT_AUTO_DELETE_MINUTES", 0)),),
            )

            # Seed default message templates
            for key, val in DEFAULT_MESSAGES.items():
                await conn.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO NOTHING;
                    """,
                    (key, val),
                )

            await conn.commit()
            logger.info("Database schema initialized and baseline seeded at %s", self.db_path)

    async def backup(self, destination: Path) -> Path:
        """Create an online backup of the SQLite database using sqlite3 backup API."""
        import asyncio
        import sqlite3

        def _sync_backup():
            destination.parent.mkdir(parents=True, exist_ok=True)
            src = sqlite3.connect(self.db_path)
            dst = sqlite3.connect(destination)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()

        await asyncio.to_thread(_sync_backup)
        logger.info("Database backup created at %s", destination)
        return destination
