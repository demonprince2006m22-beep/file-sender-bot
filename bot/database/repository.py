"""Data access repository for File Sender Bot."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import aiosqlite

from bot.database.db import Database
from bot.database.models import (
    AdminUser,
    AuditLogEntry,
    DeliveryRecord,
    FileRecord,
    RequiredChannel,
)

logger = logging.getLogger(__name__)


def _parse_datetime(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        # Handle SQLite ISO strings
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


class Repository:
    """Async repository for all database entities."""

    def __init__(self, db: Database):
        self.db = db

    # ==================== FILES ====================

    async def create_file(self, file: FileRecord) -> FileRecord:
        """Insert a new file record."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO files (
                    link_token, file_id, file_unique_id, file_name,
                    media_type, file_size, mime_type, caption,
                    storage_channel_id, storage_message_id, status,
                    expires_at, delivery_limit, delivery_count,
                    auto_delete_minutes, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file.link_token,
                    file.file_id,
                    file.file_unique_id,
                    file.file_name,
                    file.media_type,
                    file.file_size,
                    file.mime_type,
                    file.caption,
                    file.storage_channel_id,
                    file.storage_message_id,
                    file.status,
                    file.expires_at.isoformat() if file.expires_at else None,
                    file.delivery_limit,
                    file.delivery_count,
                    file.auto_delete_minutes,
                    file.created_by,
                ),
            )
            file.id = cursor.lastrowid
            await conn.commit()
            return file

    async def get_file_by_token(self, token: str) -> Optional[FileRecord]:
        """Fetch a file by unique link token."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM files WHERE link_token = ?
                """,
                (token,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_file(row)

    async def get_file_by_id(self, file_id: int) -> Optional[FileRecord]:
        """Fetch a file by primary ID."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM files WHERE id = ?
                """,
                (file_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_file(row)

    async def list_files(
        self,
        limit: int = 10,
        offset: int = 0,
        search: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[FileRecord], int]:
        """List files with optional filtering and pagination."""
        query = "SELECT * FROM files WHERE 1=1"
        count_query = "SELECT COUNT(*) FROM files WHERE 1=1"
        params: List[Any] = []
        count_params: List[Any] = []

        if search:
            query += " AND (file_name LIKE ? OR link_token LIKE ?)"
            count_query += " AND (file_name LIKE ? OR link_token LIKE ?)"
            pattern = f"%{search}%"
            params.extend([pattern, pattern])
            count_params.extend([pattern, pattern])

        if status:
            query += " AND status = ?"
            count_query += " AND status = ?"
            params.append(status)
            count_params.append(status)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self.db.connection() as conn:
            cursor = await conn.execute(count_query, count_params)
            total = (await cursor.fetchone())[0]

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            files = [self._row_to_file(row) for row in rows]
            return files, total

    async def update_file_status(self, file_id: int, status: str) -> bool:
        """Update file status ('active', 'disabled', 'deleted')."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE files
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, file_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_file_token(self, file_id: int, new_token: str) -> bool:
        """Regenerate link token for a file."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE files
                SET link_token = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_token, file_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_file_expiry(
        self, file_id: int, expires_at: Optional[datetime]
    ) -> bool:
        """Update file expiration timestamp."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE files
                SET expires_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (expires_at.isoformat() if expires_at else None, file_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_file_delivery_limit(
        self, file_id: int, limit: Optional[int]
    ) -> bool:
        """Update per-user or link delivery limit."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE files
                SET delivery_limit = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (limit, file_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_file(self, file_id: int) -> bool:
        """Mark file as deleted or remove record."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE files
                SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (file_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def increment_delivery_count(self, file_id: int) -> None:
        """Increment overall delivery count for a file."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                UPDATE files
                SET delivery_count = delivery_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (file_id,),
            )
            await conn.commit()

    async def update_file_auto_delete(
        self, file_id: int, auto_delete_minutes: Optional[int]
    ) -> bool:
        """Update file auto-delete timer in minutes (None / 0 / positive integer)."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE files
                SET auto_delete_minutes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (auto_delete_minutes, file_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    def _row_to_file(self, row: aiosqlite.Row) -> FileRecord:
        keys = row.keys()
        return FileRecord(
            id=row["id"],
            link_token=row["link_token"],
            file_id=row["file_id"],
            file_unique_id=row["file_unique_id"],
            file_name=row["file_name"],
            media_type=row["media_type"],
            file_size=row["file_size"],
            mime_type=row["mime_type"],
            caption=row["caption"],
            storage_channel_id=row["storage_channel_id"],
            storage_message_id=row["storage_message_id"],
            status=row["status"],
            expires_at=_parse_datetime(row["expires_at"]),
            delivery_limit=row["delivery_limit"],
            delivery_count=row["delivery_count"],
            auto_delete_minutes=row["auto_delete_minutes"] if "auto_delete_minutes" in keys else None,
            created_by=row["created_by"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    # ==================== REQUIRED CHANNELS ====================

    async def add_required_channel(self, channel: RequiredChannel) -> RequiredChannel:
        """Add or update a required channel."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO required_channels (channel_id, display_name, join_url, is_enabled, added_by)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    join_url = excluded.join_url,
                    is_enabled = excluded.is_enabled,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    channel.channel_id,
                    channel.display_name,
                    channel.join_url,
                    1 if channel.is_enabled else 0,
                    channel.added_by,
                ),
            )
            channel.id = cursor.lastrowid
            await conn.commit()
            return channel

    async def get_required_channel(self, channel_id: int) -> Optional[RequiredChannel]:
        """Fetch a required channel by channel ID."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM required_channels WHERE channel_id = ?
                """,
                (channel_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_channel(row)

    async def list_required_channels(
        self, only_enabled: bool = False
    ) -> List[RequiredChannel]:
        """List required channels."""
        query = "SELECT * FROM required_channels"
        if only_enabled:
            query += " WHERE is_enabled = 1"
        query += " ORDER BY id ASC"

        async with self.db.connection() as conn:
            cursor = await conn.execute(query)
            rows = await cursor.fetchall()
            return [self._row_to_channel(row) for row in rows]

    async def update_channel_status(self, channel_id: int, is_enabled: bool) -> bool:
        """Enable or disable a required channel."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE required_channels
                SET is_enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE channel_id = ?
                """,
                (1 if is_enabled else 0, channel_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def update_channel_details(
        self, channel_id: int, display_name: str, join_url: str
    ) -> bool:
        """Update channel display name and join URL."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE required_channels
                SET display_name = ?, join_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE channel_id = ?
                """,
                (display_name, join_url, channel_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_required_channel(self, channel_id: int) -> bool:
        """Remove a required channel."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM required_channels WHERE channel_id = ?
                """,
                (channel_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    def _row_to_channel(self, row: aiosqlite.Row) -> RequiredChannel:
        return RequiredChannel(
            id=row["id"],
            channel_id=row["channel_id"],
            display_name=row["display_name"],
            join_url=row["join_url"],
            is_enabled=bool(row["is_enabled"]),
            added_by=row["added_by"],
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    # ==================== ADMINS ====================

    async def get_all_admin_ids(self) -> Set[int]:
        """Fetch all authorized admin Telegram IDs."""
        async with self.db.connection() as conn:
            cursor = await conn.execute("SELECT telegram_id FROM admins")
            rows = await cursor.fetchall()
            return {row["telegram_id"] for row in rows}

    async def is_admin(self, telegram_id: int) -> bool:
        """Check if Telegram ID belongs to an authorized admin."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,)
            )
            return (await cursor.fetchone()) is not None

    async def is_owner(self, telegram_id: int) -> bool:
        """Check if Telegram ID belongs to the owner."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM admins WHERE telegram_id = ? AND role = 'owner'",
                (telegram_id,),
            )
            return (await cursor.fetchone()) is not None

    async def add_admin(
        self, telegram_id: int, role: str = "admin", added_by: Optional[int] = None
    ) -> bool:
        """Add a new admin."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO admins (telegram_id, role, added_by)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET role = excluded.role
                """,
                (telegram_id, role, added_by),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def remove_admin(self, telegram_id: int) -> bool:
        """Remove an admin (cannot remove owner)."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM admins WHERE telegram_id = ? AND role != 'owner'",
                (telegram_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def list_admins(self) -> List[AdminUser]:
        """List all admins."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM admins ORDER BY role DESC, id ASC"
            )
            rows = await cursor.fetchall()
            return [
                AdminUser(
                    id=row["id"],
                    telegram_id=row["telegram_id"],
                    role=row["role"],
                    added_by=row["added_by"],
                    created_at=_parse_datetime(row["created_at"]),
                )
                for row in rows
            ]

    # ==================== DELIVERIES ====================

    async def record_delivery(self, file_id: int, user_id: int) -> None:
        """Record a successful delivery to a user."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO deliveries (file_id, user_id)
                VALUES (?, ?)
                """,
                (file_id, user_id),
            )
            await conn.execute(
                """
                UPDATE files
                SET delivery_count = delivery_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (file_id,),
            )
            await conn.commit()

    async def get_user_delivery_count(self, file_id: int, user_id: int) -> int:
        """Get how many times a user has downloaded this specific file."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) FROM deliveries
                WHERE file_id = ? AND user_id = ?
                """,
                (file_id, user_id),
            )
            return (await cursor.fetchone())[0]

    async def get_total_delivery_count(self) -> int:
        """Get total count of all deliveries ever made."""
        async with self.db.connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM deliveries")
            return (await cursor.fetchone())[0]

    async def get_recent_deliveries(self, limit: int = 10) -> List[DeliveryRecord]:
        """Get recent delivery log."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT d.*, f.file_name
                FROM deliveries d
                LEFT JOIN files f ON d.file_id = f.id
                ORDER BY d.id DESC LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                DeliveryRecord(
                    id=row["id"],
                    file_id=row["file_id"],
                    user_id=row["user_id"],
                    delivered_at=_parse_datetime(row["delivered_at"]),
                    file_name=row["file_name"],
                )
                for row in rows
            ]

    # ==================== SETTINGS ====================

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch a single setting value."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row:
                return row["value"]
            return default

    async def set_setting(self, key: str, value: str) -> None:
        """Store or update a setting value."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            await conn.commit()

    async def get_all_settings(self) -> Dict[str, str]:
        """Fetch all settings as a dict."""
        async with self.db.connection() as conn:
            cursor = await conn.execute("SELECT key, value FROM settings")
            rows = await cursor.fetchall()
            return {row["key"]: row["value"] for row in rows}

    # ==================== AUDIT LOGS ====================

    async def log_action(
        self,
        admin_id: int,
        action: str,
        target: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Record an administrative action into the audit trail."""
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO audit_logs (admin_id, action, target, details)
                VALUES (?, ?, ?, ?)
                """,
                (admin_id, action, str(target) if target else None, details),
            )
            await conn.commit()

    async def get_recent_audit_logs(self, limit: int = 15) -> List[AuditLogEntry]:
        """Get recent admin audit log records."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM audit_logs
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                AuditLogEntry(
                    id=row["id"],
                    admin_id=row["admin_id"],
                    action=row["action"],
                    target=row["target"],
                    details=row["details"],
                    created_at=_parse_datetime(row["created_at"]),
                )
                for row in rows
            ]

    # ==================== OVERVIEW & STATS ====================

    async def get_overview_stats(self) -> Dict[str, Any]:
        """Fetch aggregated metrics for admin overview dashboard."""
        async with self.db.connection() as conn:
            # Files counts
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as total_files,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_files,
                    SUM(CASE WHEN status = 'disabled' THEN 1 ELSE 0 END) as disabled_files,
                    SUM(CASE WHEN status = 'deleted' THEN 1 ELSE 0 END) as deleted_files
                FROM files
                """
            )
            files_row = await cursor.fetchone()

            # Channels counts
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as total_channels,
                    SUM(CASE WHEN is_enabled = 1 THEN 1 ELSE 0 END) as enabled_channels
                FROM required_channels
                """
            )
            channels_row = await cursor.fetchone()

            # Deliveries count and unique users
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as total_deliveries,
                    COUNT(DISTINCT user_id) as unique_users
                FROM deliveries
                """
            )
            deliv_row = await cursor.fetchone()

            # Admin count
            cursor = await conn.execute("SELECT COUNT(*) FROM admins")
            admin_count = (await cursor.fetchone())[0]

            return {
                "total_files": files_row["total_files"] or 0,
                "active_files": files_row["active_files"] or 0,
                "disabled_files": files_row["disabled_files"] or 0,
                "deleted_files": files_row["deleted_files"] or 0,
                "total_channels": channels_row["total_channels"] or 0,
                "enabled_channels": channels_row["enabled_channels"] or 0,
                "total_deliveries": deliv_row["total_deliveries"] or 0,
                "unique_users": deliv_row["unique_users"] or 0,
                "admin_count": admin_count or 0,
            }

    # ==================== PENDING DELETIONS ====================

    async def add_pending_deletion(
        self, chat_id: int, message_id: int, delete_at: datetime
    ) -> int:
        """Schedule a message deletion in database."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO pending_deletions (chat_id, message_id, delete_at)
                VALUES (?, ?, ?)
                """,
                (chat_id, message_id, delete_at.isoformat()),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_due_deletions(
        self, before: Optional[datetime] = None
    ) -> List[Tuple[int, int, int]]:
        """Retrieve pending deletions that are due (id, chat_id, message_id)."""
        now_dt = before or datetime.now(timezone.utc)
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, chat_id, message_id, delete_at FROM pending_deletions
                ORDER BY delete_at ASC
                LIMIT 100
                """
            )
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                dt = _parse_datetime(r["delete_at"])
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt <= now_dt:
                        results.append((r["id"], r["chat_id"], r["message_id"]))
            return results

    async def delete_pending_deletion(self, deletion_id: int) -> bool:
        """Remove a completed deletion from pending list."""
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM pending_deletions WHERE id = ?",
                (deletion_id,),
            )
            await conn.commit()
            return cursor.rowcount > 0

