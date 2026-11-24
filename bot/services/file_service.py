"""Service handling file storage, token generation, link resolution, and delivery limits."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Tuple

from aiogram import Bot
from aiogram.types import Message

from bot.database.models import FileRecord
from bot.database.repository import Repository

logger = logging.getLogger(__name__)


class FileAccessStatus(str, Enum):
    ALLOWED = "allowed"
    NOT_FOUND = "not_found"
    DISABLED = "disabled"
    DELETED = "deleted"
    EXPIRED = "expired"
    LIMIT_REACHED = "limit_reached"


def generate_secure_token(length_bytes: int = 16) -> str:
    """Generate a cryptographically secure, URL-safe random token."""
    return secrets.token_urlsafe(length_bytes)


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string (KB, MB, GB)."""
    if not size_bytes or size_bytes <= 0:
        return "Unknown size"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def extract_media_info(message: Message) -> Tuple[str, str, str, str, int, Optional[str]]:
    """Extract media type, file_id, file_unique_id, file_name, file_size, and mime_type."""
    if message.document:
        doc = message.document
        return (
            "document",
            doc.file_id,
            doc.file_unique_id,
            doc.file_name or "document",
            doc.file_size or 0,
            doc.mime_type,
        )
    elif message.video:
        vid = message.video
        return (
            "video",
            vid.file_id,
            vid.file_unique_id,
            vid.file_name or "video.mp4",
            vid.file_size or 0,
            vid.mime_type or "video/mp4",
        )
    elif message.audio:
        aud = message.audio
        name = aud.file_name or f"{aud.performer or 'Audio'} - {aud.title or 'track'}"
        return (
            "audio",
            aud.file_id,
            aud.file_unique_id,
            name,
            aud.file_size or 0,
            aud.mime_type or "audio/mpeg",
        )
    elif message.photo:
        # Photo is a list of PhotoSize, largest is at the end
        photo = message.photo[-1]
        return (
            "photo",
            photo.file_id,
            photo.file_unique_id,
            f"photo_{photo.file_unique_id[:8]}.jpg",
            photo.file_size or 0,
            "image/jpeg",
        )
    elif message.animation:
        anim = message.animation
        return (
            "animation",
            anim.file_id,
            anim.file_unique_id,
            anim.file_name or "animation.gif",
            anim.file_size or 0,
            anim.mime_type or "image/gif",
        )
    elif message.voice:
        voice = message.voice
        return (
            "voice",
            voice.file_id,
            voice.file_unique_id,
            f"voice_{voice.file_unique_id[:8]}.ogg",
            voice.file_size or 0,
            voice.mime_type or "audio/ogg",
        )
    elif message.video_note:
        vn = message.video_note
        return (
            "video_note",
            vn.file_id,
            vn.file_unique_id,
            f"videonote_{vn.file_unique_id[:8]}.mp4",
            vn.file_size or 0,
            "video/mp4",
        )
    else:
        raise ValueError("Unsupported media type. Please send a document, video, audio, or photo.")


class FileService:
    """Business logic for file management and access links."""

    def __init__(self, repo: Repository):
        self.repo = repo

    async def store_file_from_message(
        self,
        bot: Bot,
        message: Message,
        admin_id: int,
        storage_channel_id: int,
        expiry_hours: Optional[int] = None,
        delivery_limit: Optional[int] = None,
    ) -> Tuple[FileRecord, str]:
        """
        Copies file message to the private storage channel, saves metadata in database,
        and generates a unique deep link token.
        """
        # 1. Extract media details
        media_type, file_id, file_unique_id, file_name, file_size, mime_type = (
            extract_media_info(message)
        )
        caption = message.caption

        # 2. Copy message to private storage channel
        try:
            copied_msg = await bot.copy_message(
                chat_id=storage_channel_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            storage_message_id = copied_msg.message_id
        except Exception as e:
            logger.error("Failed to copy message to storage channel %s: %s", storage_channel_id, e)
            raise RuntimeError(
                f"Could not copy file to storage channel: {e}. Please ensure the bot is an administrator in the storage channel with 'Post Messages' permission."
            ) from e

        # 3. Compute expiry if requested
        expires_at = None
        if expiry_hours and expiry_hours > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)

        # 4. Generate unique unguessable token
        token = generate_secure_token()

        # 5. Save to database
        record = FileRecord(
            link_token=token,
            file_id=file_id,
            file_unique_id=file_unique_id,
            file_name=file_name,
            media_type=media_type,
            file_size=file_size,
            mime_type=mime_type,
            caption=caption,
            storage_channel_id=storage_channel_id,
            storage_message_id=storage_message_id,
            status="active",
            expires_at=expires_at,
            delivery_limit=delivery_limit,
            delivery_count=0,
            created_by=admin_id,
        )

        saved = await self.repo.create_file(record)
        return saved, token

    async def evaluate_access(
        self, token: str, user_id: int
    ) -> Tuple[FileAccessStatus, Optional[FileRecord]]:
        """
        Evaluate if a user is eligible to receive the file identified by token.
        Checks: existence, active status, expiration, per-user delivery limits.
        """
        file = await self.repo.get_file_by_token(token)
        if not file:
            return FileAccessStatus.NOT_FOUND, None

        if file.status == "deleted":
            return FileAccessStatus.DELETED, file

        if file.status == "disabled":
            return FileAccessStatus.DISABLED, file

        if file.is_expired():
            return FileAccessStatus.EXPIRED, file

        # Check delivery limits if configured
        if file.delivery_limit is not None and file.delivery_limit > 0:
            user_deliveries = await self.repo.get_user_delivery_count(file.id, user_id)
            if user_deliveries >= file.delivery_limit:
                return FileAccessStatus.LIMIT_REACHED, file

        return FileAccessStatus.ALLOWED, file

    async def deliver_file_to_user(
        self,
        bot: Bot,
        user_id: int,
        file: FileRecord,
        caption: Optional[str] = None,
    ) -> Message:
        """
        Deliver file to user by copying from private storage channel (or fallback send).
        Updates delivery records.
        """
        try:
            # Prefer copying message from storage channel to retain original attributes/caption
            kwargs = {}
            if caption is not None:
                kwargs["caption"] = caption

            sent_msg = await bot.copy_message(
                chat_id=user_id,
                from_chat_id=file.storage_channel_id,
                message_id=file.storage_message_id,
                **kwargs,
            )
        except Exception as copy_err:
            logger.warning(
                "copy_message failed (%s), attempting fallback send using file_id",
                copy_err,
            )
            delivery_caption = caption if caption is not None else file.caption
            # Fallback by file_id if original message in storage channel was touched or copy_message restricted
            if file.media_type == "video":
                sent_msg = await bot.send_video(
                    chat_id=user_id, video=file.file_id, caption=delivery_caption
                )
            elif file.media_type == "audio":
                sent_msg = await bot.send_audio(
                    chat_id=user_id, audio=file.file_id, caption=delivery_caption
                )
            elif file.media_type == "photo":
                sent_msg = await bot.send_photo(
                    chat_id=user_id, photo=file.file_id, caption=delivery_caption
                )
            elif file.media_type == "animation":
                sent_msg = await bot.send_animation(
                    chat_id=user_id, animation=file.file_id, caption=delivery_caption
                )
            else:
                sent_msg = await bot.send_document(
                    chat_id=user_id, document=file.file_id, caption=delivery_caption
                )

        # Record delivery
        if file.id:
            await self.repo.record_delivery(file.id, user_id)

        return sent_msg

