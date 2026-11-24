"""Inline keyboards for the Admin Panel."""

from typing import List, Optional
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.database.models import AdminUser, FileRecord, RequiredChannel


def build_admin_main_menu(is_owner: bool = False) -> InlineKeyboardMarkup:
    """Build the main admin panel dashboard keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="📊 Overview", callback_data="admin:overview"),
            InlineKeyboardButton(text="📢 Channels", callback_data="admin:channels:list"),
        ],
        [
            InlineKeyboardButton(text="💾 Storage Channel", callback_data="admin:storage"),
            InlineKeyboardButton(text="📁 Files & Links", callback_data="admin:files:p:0"),
        ],
        [
            InlineKeyboardButton(text="💬 Message Templates", callback_data="admin:templates"),
            InlineKeyboardButton(text="⚙️ Settings", callback_data="admin:settings"),
        ],
    ]

    extra_row = [
        InlineKeyboardButton(text="📋 Audit Logs", callback_data="admin:audit")
    ]
    if is_owner:
        extra_row.insert(0, InlineKeyboardButton(text="👥 Manage Admins", callback_data="admin:admins"))

    buttons.append(extra_row)
    buttons.append([InlineKeyboardButton(text="❌ Close Panel", callback_data="admin:close")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_back_button(target: str = "admin:menu") -> InlineKeyboardMarkup:
    """Standard back button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data=target)]]
    )


def build_cancel_fsm_button(target: str = "admin:menu") -> InlineKeyboardMarkup:
    """Cancel in-progress FSM action button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel Action", callback_data=f"fsm:cancel:{target}")]]
    )


def build_confirmation_keyboard(
    confirm_data: str, cancel_data: str = "admin:menu"
) -> InlineKeyboardMarkup:
    """Generic confirmation keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Confirm", callback_data=confirm_data),
                InlineKeyboardButton(text="❌ Cancel", callback_data=cancel_data),
            ]
        ]
    )


# ==================== CHANNELS KEYBOARDS ====================


def build_channels_list_keyboard(channels: List[RequiredChannel]) -> InlineKeyboardMarkup:
    """Keyboard listing all required channels with an Add Channel button."""
    buttons = []
    for ch in channels:
        status_icon = "🟢" if ch.is_enabled else "🔴"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {ch.display_name} ({ch.channel_id})",
                    callback_data=f"admin:chan:view:{ch.channel_id}",
                )
            ]
        )

    buttons.append([InlineKeyboardButton(text="➕ Add Required Channel", callback_data="admin:chan:add")])
    buttons.append([InlineKeyboardButton(text="🔙 Main Panel", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_channel_detail_keyboard(channel: RequiredChannel) -> InlineKeyboardMarkup:
    """Keyboard for managing a single channel."""
    toggle_text = "🔴 Disable Channel" if channel.is_enabled else "🟢 Enable Channel"
    buttons = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"admin:chan:toggle:{channel.channel_id}"),
            InlineKeyboardButton(text="🔍 Test Permissions", callback_data=f"admin:chan:test:{channel.channel_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Edit Display Name", callback_data=f"admin:chan:edit_name:{channel.channel_id}"),
            InlineKeyboardButton(text="🔗 Edit Join URL", callback_data=f"admin:chan:edit_url:{channel.channel_id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Delete Channel", callback_data=f"admin:chan:del_conf:{channel.channel_id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Channels", callback_data="admin:channels:list"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== STORAGE KEYBOARDS ====================


def build_storage_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for storage channel management."""
    buttons = [
        [
            InlineKeyboardButton(text="🔍 Test Bot Permissions", callback_data="admin:storage:test"),
            InlineKeyboardButton(text="✏️ Change Storage Channel", callback_data="admin:storage:change"),
        ],
        [
            InlineKeyboardButton(text="🔙 Main Panel", callback_data="admin:menu"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== FILES KEYBOARDS ====================


def build_files_list_keyboard(
    files: List[FileRecord], page: int, total_pages: int, search: Optional[str] = None
) -> InlineKeyboardMarkup:
    """Paginated list of files."""
    buttons = []
    for f in files:
        status_icon = "🟢" if f.status == "active" else ("🟡" if f.status == "disabled" else "🔴")
        display = f.file_name or f"File #{f.id}"
        if len(display) > 28:
            display = display[:25] + "..."
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_icon} {display}",
                    callback_data=f"admin:file:view:{f.id}",
                )
            ]
        )

    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin:files:p:{page - 1}")
        )
    nav_row.append(
        InlineKeyboardButton(
            text=f"📄 {page + 1}/{max(1, total_pages)}", callback_data="noop"
        )
    )
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Next ➡️", callback_data=f"admin:files:p:{page + 1}")
        )
    buttons.append(nav_row)

    search_text = "🔍 Search Files" if not search else f"🔍 Filter: '{search}' (Clear)"
    buttons.append(
        [
            InlineKeyboardButton(text=search_text, callback_data="admin:files:search"),
        ]
    )
    buttons.append([InlineKeyboardButton(text="🔙 Main Panel", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_file_detail_keyboard(file: FileRecord) -> InlineKeyboardMarkup:
    """Keyboard for managing a specific file."""
    toggle_text = "🟡 Disable Link" if file.status == "active" else "🟢 Enable Link"
    buttons = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data=f"admin:file:toggle:{file.id}"),
            InlineKeyboardButton(text="🔄 Regenerate Link", callback_data=f"admin:file:regen:{file.id}"),
        ],
        [
            InlineKeyboardButton(text="⏱ Set Expiration", callback_data=f"admin:file:expiry:{file.id}"),
            InlineKeyboardButton(text="🛑 Set Delivery Limit", callback_data=f"admin:file:limit:{file.id}"),
        ],
        [
            InlineKeyboardButton(text="🗑 Set Auto-Delete", callback_data=f"admin:file:autodel:{file.id}"),
            InlineKeyboardButton(text="🗑 Delete Record", callback_data=f"admin:file:del_conf:{file.id}"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Files", callback_data="admin:files:p:0"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== TEMPLATES & SETTINGS KEYBOARDS ====================


def build_templates_menu_keyboard() -> InlineKeyboardMarkup:
    """Keyboard listing customizable message templates."""
    buttons = [
        [InlineKeyboardButton(text="👋 Welcome Message", callback_data="admin:tpl:msg_welcome")],
        [InlineKeyboardButton(text="⚠️ Subscription Prompt", callback_data="admin:tpl:msg_sub_prompt")],
        [InlineKeyboardButton(text="✅ Success Message", callback_data="admin:tpl:msg_success")],
        [InlineKeyboardButton(text="❌ Invalid Link Message", callback_data="admin:tpl:msg_invalid_link")],
        [InlineKeyboardButton(text="⌛ Expired Link Message", callback_data="admin:tpl:msg_expired_link")],
        [InlineKeyboardButton(text="🛑 Delivery Limit Message", callback_data="admin:tpl:msg_limit_reached")],
        [InlineKeyboardButton(text="⏳ Auto-Delete Notice", callback_data="admin:tpl:msg_auto_delete_notice")],
        [InlineKeyboardButton(text="ℹ️ Help Message", callback_data="admin:tpl:msg_help")],
        [InlineKeyboardButton(text="🔙 Main Panel", callback_data="admin:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_template_actions_keyboard(template_key: str) -> InlineKeyboardMarkup:
    """Keyboard for viewing/editing a single template."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Edit Template", callback_data=f"admin:tpledit:{template_key}"
                ),
                InlineKeyboardButton(
                    text="🔄 Reset to Default", callback_data=f"admin:tplreset:{template_key}"
                ),
            ],
            [InlineKeyboardButton(text="🔙 Back to Templates", callback_data="admin:templates")],
        ]
    )


def build_settings_menu_keyboard(force_sub: bool) -> InlineKeyboardMarkup:
    """Keyboard for behavior configuration."""
    force_sub_icon = "🟢 Enabled" if force_sub else "🔴 Disabled"
    buttons = [
        [
            InlineKeyboardButton(
                text=f"Force Subscription: {force_sub_icon}",
                callback_data="admin:set:toggle_forcesub",
            )
        ],
        [
            InlineKeyboardButton(
                text="⏱ Edit Default Link Expiry", callback_data="admin:set:expiry"
            ),
            InlineKeyboardButton(
                text="🛑 Edit Default Delivery Limit", callback_data="admin:set:limit"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🗑 Edit Auto-Delete Timer", callback_data="admin:set:autodel"
            ),
        ],
        [InlineKeyboardButton(text="🔙 Main Panel", callback_data="admin:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== ADMINS MANAGEMENT KEYBOARDS ====================


def build_admins_menu_keyboard(admins: List[AdminUser], current_owner_id: int) -> InlineKeyboardMarkup:
    """Keyboard listing all admins with add/remove buttons."""
    buttons = []
    for adm in admins:
        role_label = "👑 Owner" if adm.role == "owner" else "🛡 Admin"
        if adm.telegram_id != current_owner_id:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{role_label} - ID: {adm.telegram_id}",
                        callback_data="noop",
                    ),
                    InlineKeyboardButton(
                        text="❌ Revoke",
                        callback_data=f"admin:rev_conf:{adm.telegram_id}",
                    ),
                ]
            )
        else:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{role_label} - ID: {adm.telegram_id} (You)",
                        callback_data="noop",
                    )
                ]
            )

    buttons.append([InlineKeyboardButton(text="➕ Add New Admin ID", callback_data="admin:add_admin")])
    buttons.append([InlineKeyboardButton(text="🔙 Main Panel", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

