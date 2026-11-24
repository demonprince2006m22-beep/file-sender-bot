-- Schema for Telegram File Sender Bot

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_token TEXT UNIQUE NOT NULL,
    file_id TEXT NOT NULL,
    file_unique_id TEXT NOT NULL,
    file_name TEXT,
    media_type TEXT NOT NULL,
    file_size INTEGER DEFAULT 0,
    mime_type TEXT,
    caption TEXT,
    storage_channel_id INTEGER NOT NULL,
    storage_message_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'disabled', 'deleted'
    expires_at TIMESTAMP NULL,
    delivery_limit INTEGER NULL,
    delivery_count INTEGER NOT NULL DEFAULT 0,
    auto_delete_minutes INTEGER NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_files_token ON files(link_token);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_files_created_by ON files(created_by);

CREATE TABLE IF NOT EXISTS required_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    join_url TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    added_by INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_channels_enabled ON required_channels(is_enabled);

CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin', -- 'owner', 'admin'
    added_by INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admins_telegram_id ON admins(telegram_id);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    delivered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deliveries_file_user ON deliveries(file_id, user_id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_admin ON audit_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

CREATE TABLE IF NOT EXISTS pending_deletions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    delete_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_delete_at ON pending_deletions(delete_at);


