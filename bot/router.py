"""
Entry point for processing a single Telegram Update object. Called by the
Vercel webhook function (api/webhook.py) for every incoming update.
"""
import logging
from bot import fsm, telegram_api
from bot.config import ADMIN_CHANNEL_ID
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

    # Hard guard: this bot only ever has real conversations in PRIVATE chats.
    # Any update whose chat is a channel or group — including "someone joined"
    # service messages, or anything else Telegram sends about activity in
    # your private client channel or admin channel — must never be treated
    # as a DM to respond to. Without this, a join event in your channel could
    # get misread as "this person messaged the bot" and the bot would reply
    # publicly into that channel instead of privately to the user.
    if chat.get("type") != "private":
        return

    # (Belt-and-suspenders: the admin channel is a channel, so the check
    # above already excludes it, but this stays as an explicit safeguard.)
    if str(chat["id"]) == str(ADMIN_CHANNEL_ID):
        return

    # --- Everything else is a private DM from a regular user (or an admin) ---
    telegram_id = message["from"]["id"]
    user = message["from"]
    queries.get_or_create_user(telegram_id, user.get("username"), user.get("first_name"))

    text = message.get("text", "")

    if text.startswith("/start"):
        start.handle_start(message)
        return

    # If this admin has a pending "type your reply" action queued (from
    # clicking Need More Info or Reply on a ticket), consume it here first —
    # takes priority over everything else in their DM.
    if admin.is_admin(telegram_id) and "text" in message:
        if admin.handle_admin_dm_text(message):
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
