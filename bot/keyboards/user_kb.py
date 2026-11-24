"""Inline keyboards for user interactions."""

from typing import List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import RequiredChannel


def build_subscription_keyboard(
    missing_channels: List[RequiredChannel],
    token: str,
    check_button_text: str = "🔄 Check again",
    join_button_template: str = "📢 Join {channel_name}",
) -> InlineKeyboardMarkup:
    """Build keyboard presenting join links for each missing channel and a re-verify button."""
    buttons: List[List[InlineKeyboardButton]] = []

    for ch in missing_channels:
        label = join_button_template.replace("{channel_name}", ch.display_name)
        buttons.append([InlineKeyboardButton(text=label, url=ch.join_url)])

    # Verification callback button carrying the file token
    buttons.append(
        [
            InlineKeyboardButton(
                text=check_button_text, callback_data=f"sub_verify:{token}"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)

