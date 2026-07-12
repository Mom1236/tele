"""
Central configuration. Everything is read from environment variables so no
secrets ever live in source code. See .env.example for the full list.
"""
import os


def _get_env(name: str, required: bool = True, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# --- Telegram ---------------------------------------------------------------
BOT_TOKEN: str = _get_env("BOT_TOKEN")
TELEGRAM_API_BASE: str = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_SECRET: str = _get_env("WEBHOOK_SECRET")  # validated against Telegram's secret header

# The private channel users must join before using the bot.
# Use the numeric ID (e.g. -1001234567890) — most reliable for getChatMember.
PRIVATE_CHANNEL_ID: str = _get_env("PRIVATE_CHANNEL_ID")
PRIVATE_CHANNEL_INVITE_LINK: str = _get_env("PRIVATE_CHANNEL_INVITE_LINK")

# The admin group where applications/support tickets are posted.
# Must be a GROUP or SUPERGROUP (not a broadcast channel) — see README.
ADMIN_GROUP_ID: str = _get_env("ADMIN_GROUP_ID")

# Comma-separated list of admin Telegram user IDs, e.g. "8521287064,111111111"
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in _get_env("ADMIN_IDS").split(",") if x.strip()
]

# --- Supabase -----------------------------------------------------------------
SUPABASE_URL: str = _get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str = _get_env("SUPABASE_SERVICE_KEY")

# --- Rate limits --------------------------------------------------------------
MAX_ACTIVE_APPLICATIONS = 3
NEW_APPLICATION_COOLDOWN_SECONDS = 10 * 60          # 1 new application / 10 min
MAX_BUTTON_PRESSES_PER_WINDOW = 5
BUTTON_WINDOW_SECONDS = 10
MAX_FORM_MESSAGES_PER_WINDOW = 10
FORM_MESSAGE_WINDOW_SECONDS = 60

# --- Misc -----------------------------------------------------------------
MAX_IMAGES_PER_APPLICATION = 10
