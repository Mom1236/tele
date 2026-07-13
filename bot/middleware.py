"""
Cross-cutting checks applied before handlers run: channel membership and
rate limiting. Kept out of individual handlers so the rules are enforced
consistently everywhere.
"""
import logging
from bot import telegram_api, texts, keyboards
from bot.config import PRIVATE_CHANNEL_ID
from db import queries

logger = logging.getLogger("middleware")


def check_membership_live(telegram_id: int) -> bool:
    """Hits the Telegram API directly — used at /start and on 'I've Joined'."""
    result = telegram_api.get_chat_member(PRIVATE_CHANNEL_ID, telegram_id)
    if not result.get("ok"):
        logger.warning(
            "getChatMember failed for user %s in channel %s: %s",
            telegram_id, PRIVATE_CHANNEL_ID, result,
        )
        return False
    status = result.get("result", {}).get("status")
    is_member = telegram_api.is_member_status(status)
    logger.info("Membership check for user %s: status=%s -> is_member=%s", telegram_id, status, is_member)
    return is_member


def require_verified(telegram_id: int, chat_id: int) -> bool:
    """
    Fast path: trust the cached is_verified flag rather than hitting the
    Telegram API on every single message. Membership is re-checked live only
    at /start and when the user presses "I've Joined".
    """
    if queries.is_user_verified(telegram_id):
        return True
    telegram_api.send_message(chat_id, texts.NOT_A_MEMBER, keyboards.verification_keyboard())
    return False


def enforce_button_rate_limit(telegram_id: int, callback_query_id: str) -> bool:
    allowed = queries.check_and_record_button_press(telegram_id)
    if not allowed:
        telegram_api.answer_callback_query(callback_query_id, texts.RATE_LIMITED, show_alert=True)
    return allowed


def enforce_form_message_rate_limit(telegram_id: int, chat_id: int) -> bool:
    allowed = queries.check_and_record_form_message(telegram_id)
    if not allowed:
        telegram_api.send_message(chat_id, texts.RATE_LIMITED)
    return allowed
