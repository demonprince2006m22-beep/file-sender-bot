"""CLI script to create an online snapshot backup of the bot SQLite database."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import get_settings
from bot.database.db import Database


async def run_backup():
    settings = get_settings()
    db = Database(settings.DATABASE_PATH)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("backups")
    backup_file = backup_dir / f"bot_backup_{timestamp}.db"

    print(f"Starting online backup of {settings.DATABASE_PATH}...")
    saved_path = await db.backup(backup_file)
    print(f"✅ Backup created successfully at: {saved_path}")


if __name__ == "__main__":
    asyncio.run(run_backup())

