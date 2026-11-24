# 🤖 Telegram File Sender & Channel Gatekeeper Bot

A production-ready Telegram Bot built with **Python 3**, **aiogram 3**, and **SQLite (aiosqlite / WAL mode)**. The bot enables administrators to store media files in a secure, private Telegram channel and share them with users through unguessable deep links. Users are required to join all configured required channels before the bot releases the file.

---

## 🌟 Key Features

### 📤 Admin File Storage & Link Generation
- **Direct Media Uploads**: Authorized admins can simply send or forward any file, video, audio, photo, voice note, animation, or document directly to the bot.
- **Private Channel Archiving**: The bot automatically copies the media to a private storage channel. Regular users never see or receive direct links to the storage channel or message IDs.
- **Unguessable Deep Links**: Generates high-entropy, URL-safe tokens (`https://t.me/<bot_username>?start=<token>`) that prevent brute-force enumeration.
- **Optional Link Controls**: Supports configurable link expirations (hours/days) and per-user download limits.
- **⏳ Auto-Delete Self-Destruct**: Automatically purges delivered files from users' private chats after a customizable timer (e.g. 5m, 10m, 1h) to prevent copyright strikes and unauthorized sharing.

### 🛡️ Forced Subscription Verification (Gatekeeping)
- **Multi-Channel Verification**: Checks Telegram membership (`getChatMember`) in real-time across all enabled required channels.
- **Interactive Subscription Prompt**: If any required channels are missing, the bot displays direct join buttons for each missing channel alongside a **🔄 Check again** button.
- **Instant Delivery**: Upon successful verification, the file is delivered directly to the user's private chat via `copy_message` (preserving original captions, spoilers, and media formatting).
- **Graceful Error States**: Clear, customizable messages for invalid, disabled, expired, deleted, or rate-limited links.

### 👑 In-Bot Admin Panel & Allowlist Security
- **Strict Numeric ID Authorization**: Access is strictly guarded by Telegram numeric IDs (never usernames, which can change).
- **Owner vs. Admin Separation**: Primary Bot Owner has exclusive privileges to add and revoke admin users. Regular admins cannot escalate privileges.
- **Channels Management**: Add, remove, enable, disable, and test bot administrator permissions in required channels.
- **Storage Channel Configuration**: Configure or change the storage channel ID and test bot posting permissions on demand.
- **File & Link Management**: Paginated file browser, search by filename or token, toggle active/disabled states, regenerate link tokens, and set custom expiry or download limits.
- **Customizable Message Templates**: Edit welcome text, subscription prompts, success messages, invalid link notices, and help texts with safe placeholder interpolation (`{first_name}`, `{file_name}`, `{file_size}`).
- **Audit Logging**: Important administrative actions (channel additions, file deletions, link regenerations, permission changes) are recorded in an audit trail without storing tokens or secrets.
- **Anti-Flood & Debounce Protection**: Middleware prevents duplicate callback clicks or race conditions during verification and destructive actions.

---

## 🏗️ Architecture & Database Schema

The bot uses an asynchronous SQLite database in **Write-Ahead Logging (WAL)** mode with foreign key constraints enabled:

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     Admins      │       │ RequiredChannels│       │    Settings     │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │       │ key (PK)        │
│ telegram_id     │       │ channel_id      │       │ value           │
│ role (owner/adm)│       │ display_name    │       └─────────────────┘
│ added_by        │       │ join_url        │
└─────────────────┘       │ is_enabled      │
                          └─────────────────┘
                                   │
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│      Files      │◄──────│   Deliveries    │       │   Audit Logs    │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │       │ id (PK)         │
│ link_token (UQ) │       │ file_id (FK)    │       │ admin_id        │
│ file_id         │       │ user_id         │       │ action          │
│ file_name       │       │ delivered_at    │       │ target          │
│ media_type      │       └─────────────────┘       │ details         │
│ storage_chan_id │                                 │ created_at      │
│ storage_msg_id  │                                 └─────────────────┘
│ status          │
│ expires_at      │
│ delivery_limit  │
│ delivery_count  │
└─────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.10+** (Python 3.11, 3.12, 3.13, and 3.14 fully supported).
- A Telegram account.

### 2. Create the Telegram Bot
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts to choose a name and username.
3. Save the **HTTP API Bot Token** provided by BotFather.

### 3. Retrieve Your Numeric Telegram User ID
1. Search for [@userinfobot](https://t.me/userinfobot) or [@raw_data_bot](https://t.me/raw_data_bot) on Telegram.
2. Send any message to get your **numeric ID** (e.g., `123456789`).

### 4. Create the Storage Channel
1. In Telegram, create a new **Private Channel** (e.g., "My Bot Storage").
2. Go to Channel Info ➔ **Administrators** ➔ **Add Administrator**.
3. Add your bot and ensure **Post Messages** permission is enabled.
4. Get the channel ID: Forward a post from the channel to [@userinfobot] or use a client like Telegram Web to find the `-100...` ID (e.g., `-1001987654321`).

### 5. Create Required Subscription Channels
1. For any channel you want to require users to join, add your bot as an **Administrator**.
   > **Note**: The bot requires admin status in the channel so it can invoke the `getChatMember` API to inspect user membership.
2. Note the channel username (e.g. `@mychannel`) or numeric ID (e.g. `-1001122334455`) and public link or invite link.

---

## ⚙️ Configuration

1. Clone or download the repository:
   ```bash
   git clone <repo-url> file_sender_bot
   cd file_sender_bot
   ```

2. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

3. Edit `.env` with your actual values:
   ```env
   # Telegram Bot Token from @BotFather
   BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

   # Bot Owner Telegram numeric ID (Primary superadmin)
   OWNER_ID=123456789

   # Optional comma-separated list of additional Admin Telegram IDs
   ADMIN_IDS=987654321,112233445

   # Private Storage Channel ID (e.g. -100...)
   STORAGE_CHANNEL_ID=-1001987654321

   # Database path
   DATABASE_PATH=data/bot.db

   # Default link expiration in hours (0 = never expires)
   DEFAULT_EXPIRY_HOURS=0

   # Default per-user download limit (0 = unlimited)
   DEFAULT_DELIVERY_LIMIT=0

   # Force subscription requirement enabled by default (true/false)
   FORCE_SUB_ENABLED=true

   # Log level (DEBUG, INFO, WARNING, ERROR)
   LOG_LEVEL=INFO
   ```

---

## 💻 Running the Bot

### Local Installation

1. Create a Python virtual environment:
   ```bash
   python -m venv .venv
   ```

2. Activate the virtual environment:
   - **Linux / macOS**:
     ```bash
     source .venv/bin/activate
     ```
   - **Windows**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Start the bot:
   ```bash
   python -m bot.main
   ```

---

## 🐳 Docker & Docker Compose Deployment

### Using Docker Compose (Recommended)

1. Make sure your `.env` file is filled in.
2. Build and start the container in detached mode:
   ```bash
   docker-compose up -d --build
   ```
3. View logs:
   ```bash
   docker-compose logs -f
   ```
4. Stop the container:
   ```bash
   docker-compose down
   ```

### Using Plain Docker

```bash
# Build image
docker build -t file-sender-bot .

# Run container with persistent data volume
docker run -d \
  --name file_sender_bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  file-sender-bot
```

---

## 🐧 Systemd Deployment (Linux Server)

1. Deploy the code to `/opt/file_sender_bot`.
2. Create virtual environment and install dependencies.
3. Copy the systemd service file:
   ```bash
   sudo cp file-sender-bot.service /etc/systemd/system/file-sender-bot.service
   ```
4. Reload systemd daemon and enable service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now file-sender-bot
   ```
5. Check status:
   ```bash
   sudo systemctl status file-sender-bot
   ```

---

## 📖 Admin Guide & Commands

### Admin Commands

| Command | Description |
|---|---|
| `/start` | Opens the Admin Control Panel for admins; shows welcome text for users |
| `/panel` | Directly opens the Admin Control Panel |
| `/files` | Lists stored files with pagination, search, and detail links |
| `/channels` | Lists configured required channels with enable/disable buttons |
| `/addchannel` | Launches the interactive wizard to add a new required channel |
| `/removechannel` | Shows a list of channels for quick deletion |
| `/disable <id_or_token>` | Instantly disables a file link |
| `/help` | Shows admin command reference and upload instructions |

### User Commands

| Command | Description |
|---|---|
| `/start <token>` | Accesses a shared file, runs channel subscription checks, and delivers the file |
| `/start` | Displays standard welcome text |
| `/help` | Shows instructions on how to join required channels and access files |

---

### In-Bot Admin Panel Navigation

Access the panel via `/panel` or `/start`:

```
👑 Admin Control Panel
├── 📊 Overview            ➔ View file counts, deliveries, unique users, and recent activity
├── 📢 Channels            ➔ List, add, toggle, test bot permissions, or delete channels
├── 💾 Storage Channel     ➔ Check posting permissions or change storage channel ID
├── 📁 Files & Links       ➔ Browse files, search, toggle status, set expiry, and regenerate links
├── 💬 Message Templates   ➔ Customize welcome, prompt, success, and error templates
├── ⚙️ Settings            ➔ Toggle global force-sub and default expiry/download limits
├── 👥 Manage Admins       ➔ (Owner Only) Add or revoke admin Telegram IDs
└── 📋 Audit Logs          ➔ Inspect recent administrative actions and target IDs
```

### Template Placeholders

When customizing messages in **💬 Message Templates**, you can use these safe dynamic placeholders:

- `{first_name}`: User's Telegram first name.
- `{file_name}`: Name of the requested file.
- `{file_size}`: Formatted file size (e.g. `24.5 MB`).
- `{user_id}`: Numeric Telegram user ID.
- `{channel_name}`: Display name of the required channel (for button templates).

---

## 💾 Database Backups & Health Checks

### Live Hot Backup CLI

The bot includes a zero-downtime online backup utility using SQLite's native backup API:

```bash
python scripts/backup.py
```
This safely creates a snapshot in `backups/bot_backup_<timestamp>.db` without interrupting bot polling or active downloads.

To automate daily backups via cron:
```bash
0 3 * * * cd /opt/file_sender_bot && .venv/bin/python scripts/backup.py >> /var/log/bot_backup.log 2>&1
```

### Health Check

The `Dockerfile` includes an automated health check:
```bash
python -c "import aiosqlite; print('healthy')"
```

---

## 🔒 Security Best Practices & Telegram API Considerations

1. **Telegram File Size Limits**:
   - Telegram bots have a 20 MB download limit when downloading files from Telegram servers.
   - However, by using `bot.copy_message(chat_id, from_chat_id, message_id)`, this bot **never downloads files to the host disk**. Telegram handles file transfer internally between channels and chats, supporting files up to **2 GB** (or 4 GB with Telegram Premium)!
2. **Unguessable Tokens**:
   - Access links use `secrets.token_urlsafe(16)` which yields over 128 bits of cryptographic entropy. Tokens cannot be guessed or scanned.
3. **Required Channel Permissions**:
   - The Telegram Bot API requires bots to be an **Administrator** in a channel to invoke `getChatMember`. If the bot is only a regular subscriber, `getChatMember` will return an error. The bot's built-in **Test Permissions** button verifies this setup automatically.
4. **Rate Limits & Anti-Flood**:
   - Built-in callback debounce middleware prevents double-clicks and spamming of the **🔄 Check again** button.
   - Handles `TelegramRetryAfter` gracefully with exponential backoff.
5. **Privacy & Data Minimization**:
   - The bot records only numeric user IDs and file IDs for delivery counting and rate limits. No private messages or personal identifying data are stored.

---

## 🧪 Automated Testing

The project includes an extensive test suite using `pytest` and `pytest-asyncio`.

Run the tests:
```bash
pytest -v
```

### Test Coverage Highlights:
- ✅ **Admin Authorization**: Tests owner privileges, admin allowlist, dynamic admin addition, revocation, and rejection of unauthorized regular users.
- ✅ **Link Token Resolution**: Verifies unguessable token generation, token lookups, token regeneration (invalidating old links), and non-existent token rejection.
- ✅ **Subscription Checks**: Tests single and multi-channel verification, missing channel detection, disabled channel bypass, and global force-sub toggle.
- ✅ **Delivery Eligibility**: Validates link states (active, disabled, deleted, expired), per-user delivery limits, and delivery counter increments.
- ✅ **Template Engine**: Tests safe placeholder interpolation (`{first_name}`, `{file_name}`) and ensures unrecognized placeholders do not trigger errors.
- ✅ **Database Backup**: Validates online hot backup creation and SQLite integrity.

---

## 📄 License

This project is licensed under the MIT License.

