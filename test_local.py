"""
Local smoke test — simulates Telegram updates being POSTed to the webhook
without needing ngrok or a live deployment. Requires a real .env pointing at
your Supabase project (schema.sql already applied) since it exercises real
DB reads/writes. Telegram API calls will still go out over the network, so
use a real test bot token, or temporarily monkeypatch bot.telegram_api if you
want a fully offline test.

Usage:
    cp .env.example .env   # then fill in real values
    python test_local.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

from api.webhook import app  # noqa: E402

TEST_CHAT_ID = int(os.environ.get("TEST_CHAT_ID", "111111111"))

fake_start_update = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "from": {"id": TEST_CHAT_ID, "username": "testuser", "first_name": "Test", "is_bot": False},
        "chat": {"id": TEST_CHAT_ID, "type": "private"},
        "date": 0,
        "text": "/start",
    },
}

if __name__ == "__main__":
    client = app.test_client()
    resp = client.post(
        "/api/webhook",
        json=fake_start_update,
        headers={"X-Telegram-Bot-Api-Secret-Token": os.environ["WEBHOOK_SECRET"]},
    )
    print("Status:", resp.status_code)
    print("Body:", resp.get_json())
    print(
        "\nCheck your test bot chat with the TEST_CHAT_ID's real Telegram "
        "account to see the actual message that was sent."
    )
