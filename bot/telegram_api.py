"""
Minimal, dependency-light wrapper around the Telegram Bot HTTP API.

We deliberately avoid a heavy framework like python-telegram-bot here: on
Vercel's serverless Python runtime each request is a fresh cold-start-prone
invocation, so a plain `requests`-based wrapper keeps startup time low and
avoids fighting an async event loop inside a WSGI handler.
"""
import logging
import requests
from bot.config import TELEGRAM_API_BASE

logger = logging.getLogger("telegram_api")

_TIMEOUT = 10


def _call(method: str, payload: dict) -> dict:
    url = f"{TELEGRAM_API_BASE}/{method}"
    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        data = resp.json()
        if not data.get("ok"):
            logger.error("Telegram API error on %s: %s", method, data)
        return data
    except requests.RequestException:
        logger.exception("Network error calling Telegram method %s", method)
        return {"ok": False}


def send_message(chat_id: int | str, text: str, reply_markup: dict | None = None,
                  parse_mode: str | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return _call("sendMessage", payload)


def edit_message_text(chat_id: int | str, message_id: int, text: str,
                       reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call("editMessageText", payload)


def edit_message_reply_markup(chat_id: int | str, message_id: int,
                               reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "message_id": message_id}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call("editMessageReplyMarkup", payload)


def answer_callback_query(callback_query_id: str, text: str | None = None,
                           show_alert: bool = False) -> dict:
    payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
    if text:
        payload["text"] = text
    return _call("answerCallbackQuery", payload)


def send_photo(chat_id: int | str, file_id: str, caption: str | None = None,
                reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "photo": file_id}
    if caption:
        payload["caption"] = caption
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _call("sendPhoto", payload)


def send_document(chat_id: int | str, file_id: str, caption: str | None = None) -> dict:
    payload = {"chat_id": chat_id, "document": file_id}
    if caption:
        payload["caption"] = caption
    return _call("sendDocument", payload)


def pin_chat_message(chat_id: int | str, message_id: int, disable_notification: bool = False) -> dict:
    return _call("pinChatMessage", {
        "chat_id": chat_id, "message_id": message_id, "disable_notification": disable_notification,
    })


def get_chat_member(chat_id: int | str, user_id: int) -> dict:
    return _call("getChatMember", {"chat_id": chat_id, "user_id": user_id})


def is_member_status(status: str) -> bool:
    # Telegram membership statuses that count as "still in the chat"
    return status in ("member", "administrator", "creator")
