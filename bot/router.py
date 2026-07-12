"""
Entry point for processing a single Telegram Update object. Called by the
Vercel webhook function (api/webhook.py) for every incoming update.
"""
import logging
from bot import fsm, telegram_api
from bot.config import ADMIN_GROUP_ID
from bot.middleware import require_verified, enforce_form_message_rate_limit
from bot.handlers import start, application, support, payment, admin, callback_router
from db import queries

logger = logging.getLogger("router")


def route_update(update: dict) -> None:
    try:
        if "callback_query" in update:
            callback_router.route_callback_query(update["callback_query"])
        elif "message" in update:
            _route_message(update["message"])
    except Exception:
        logger.exception("Unhandled error processing update: %s", update)


def _route_message(message: dict) -> None:
    chat = message["chat"]
    chat_type = chat.get("type")

    # --- Messages arriving in the admin group ---
    if str(chat["id"]) == str(ADMIN_GROUP_ID) and chat_type in ("group", "supergroup"):
        _route_admin_group_message(message)
        return

    # --- Everything else is a private DM from a regular user (or an admin) ---
    telegram_id = message["from"]["id"]
    user = message["from"]
    queries.get_or_create_user(telegram_id, user.get("username"), user.get("first_name"))

    text = message.get("text", "")

    if text.startswith("/start"):
        start.handle_start(message)
        return

    if text.startswith("/") and admin.is_admin(telegram_id):
        admin.handle_admin_command(message)
        return

    if not require_verified(telegram_id, chat["id"]):
        return

    session = queries.get_session(telegram_id)
    state = session["state"]

    # Rate limit free-text messages sent while inside any multi-step flow.
    if state != fsm.IDLE and not enforce_form_message_rate_limit(telegram_id, chat["id"]):
        return

    if state in fsm.APPLICATION_FORM_SEQUENCE:
        if state == fsm.APP_IMAGES and ("photo" in message or "document" in message):
            application.handle_form_image(message, session)
        elif "text" in message:
            application.handle_form_text(message, session)
        return

    if state == fsm.AWAITING_USER_INFO_REPLY and "text" in message:
        admin.handle_user_info_reply(message, session)
        return

    if state in (fsm.AWAITING_PAYMENT_METHOD, fsm.AWAITING_CRYPTO_COIN,
                 fsm.AWAITING_CRYPTO_WALLET, fsm.AWAITING_PAYMENT_HANDLE) and "text" in message:
        payment.handle_payment_text(message, session)
        return

    if state == fsm.AWAITING_SUPPORT_MESSAGE and "text" in message:
        support.handle_support_text(message, session)
        return

    if state == fsm.AWAITING_SUPPORT_IMAGES:
        if "photo" in message or "document" in message:
            support.handle_support_image(message, session)
        elif "text" in message:
            support.handle_support_images_text(message, session)
        return

    # Idle state with plain text — nudge them back to the main menu.
    start.show_main_menu(chat["id"])


def _route_admin_group_message(message: dict) -> None:
    """
    Handles replies from admins inside the admin group: either a reply to a
    'Need More Info' prompt, or a reply to a support ticket card.
    """
    if "reply_to_message" not in message or "text" not in message:
        return
    if not admin.is_admin(message["from"]["id"]):
        return

    replied_to_id = message["reply_to_message"]["message_id"]

    pending_action = queries.get_admin_pending_action(replied_to_id)
    if pending_action:
        admin.handle_admin_reply_to_more_info_prompt(message, pending_action)
        return

    # Otherwise, check whether this is a reply to a support ticket card.
    from db.client import get_client
    ticket_res = get_client().table("support_tickets").select("*").eq(
        "admin_channel_message_id", replied_to_id
    ).execute()
    if ticket_res.data:
        admin.handle_admin_reply_to_ticket(message, ticket_res.data[0])
