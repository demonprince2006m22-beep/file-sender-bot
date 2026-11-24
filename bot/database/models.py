"""Data models for File Sender Bot."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class FileRecord:
    id: Optional[int] = None
    link_token: str = ""
    file_id: str = ""
    file_unique_id: str = ""
    file_name: Optional[str] = None
    media_type: str = "document"  # document, video, audio, photo, animation, voice, video_note
    file_size: int = 0
    mime_type: Optional[str] = None
    caption: Optional[str] = None
    storage_channel_id: int = 0
    storage_message_id: int = 0
    status: str = "active"  # active, disabled, deleted
    expires_at: Optional[datetime] = None
    delivery_limit: Optional[int] = None
    delivery_count: int = 0
    auto_delete_minutes: Optional[int] = None
    created_by: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_disabled(self) -> bool:
        return self.status == "disabled"

    @property
    def is_deleted(self) -> bool:
        return self.status == "deleted"

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        now = current_time or datetime.now(timezone.utc)
        # Handle timezone-naive/aware comparisons cleanly
        if self.expires_at.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        elif self.expires_at.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        return now > self.expires_at


@dataclass
class RequiredChannel:
    id: Optional[int] = None
    channel_id: int = 0
    display_name: str = ""
    join_url: str = ""
    is_enabled: bool = True
    added_by: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AdminUser:
    id: Optional[int] = None
    telegram_id: int = 0
    role: str = "admin"  # owner, admin
    added_by: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class DeliveryRecord:
    id: Optional[int] = None
    file_id: int = 0
    user_id: int = 0
    delivered_at: Optional[datetime] = None
    file_name: Optional[str] = None


@dataclass
class AuditLogEntry:
    id: Optional[int] = None
    admin_id: int = 0
    action: str = ""
    target: Optional[str] = None
    details: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class PendingDeletion:
    id: Optional[int] = None
    chat_id: int = 0
    message_id: int = 0
    delete_at: Optional[datetime] = None

