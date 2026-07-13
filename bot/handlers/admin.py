from bot import telegram_api, texts, keyboards, fsm
from bot.config import ADMIN_CHANNEL_ID, ADMIN_IDS
from bot.utils import status_label
from db import queries


def is_admin(telegram_id: int) -> bool:
    return telegram_id in ADMIN_IDS


# ---------------------------------------------------------------------------
# Button actions on an application card (Approve / Reject / Need More Info / Complete)
# ---------------------------------------------------------------------------
def handle_admin_application_action(callback_query: dict, action: str, code: str) -> None:
    admin_id = callback_query["from"]["id"]
    if not is_admin(admin_id):
        telegram_api.answer_callback_query(callback_query["id"], "You are not authorized to do this.", show_alert=True)
        return

    application = queries.get_application_by_code(code)
    if not application:
        telegram_api.answer_callback_query(callback_query["id"], "Application not found.", show_alert=True)
        return

    telegram_api.answer_callback_query(callback_query["id"])

    if action == "approve":
        _set_status_and_refresh(application, "approved", admin_id)
        telegram_api.send_message(application["user_id"], texts.USER_NOTICE_APPROVED)

    elif action == "reject":
        _set_status_and_refresh(application, "rejected", admin_id)
        telegram_api.send_message(application["user_id"], texts.USER_NOTICE_REJECTED)

    elif action == "complete":
        _set_status_and_refresh(application, "completed", admin_id)
        telegram_api.send_message(application["user_id"], texts.USER_NOTICE_COMPLETED)

    elif action == "moreinfo":
        telegram_api.send_message(admin_id, texts.ASK_ADMIN_MORE_INFO_TEXT.format(code=code))
        queries.set_admin_pending_action(admin_id, "awaiting_more_info_text", application["id"])


def _set_status_and_refresh(application: dict, new_status: str, admin_id: int) -> None:
    updated = queries.update_application_status(application["application_code"], new_status, changed_by=admin_id)
    _refresh_admin_card(updated)


def _refresh_admin_card(application: dict) -> None:
    """Re-renders the admin-channel card to reflect the application's CURRENT
    status without writing a new status_history row (that's handled wherever
    the status was actually changed)."""
    if not application.get("admin_channel_message_id"):
        return
    from db.client import get_client
    user_res = get_client().table("users").select("username").eq("telegram_id", application["user_id"]).execute()
    username = user_res.data[0]["username"] if user_res.data else None
    new_card = texts.admin_application_card(
        code=application["application_code"],
        username=username,
        telegram_id=application["user_id"],
        status_label=status_label(application["status"]),
        store_name=application["store_name"],
        order_number=application["order_number"],
        account_email=application["account_email"],
        verification_code=application["verification_code"],
        order_total=application["order_total"],
        tracking=application["tracking_numbers"],
        order_status=application["order_status"],
        resolution=application["desired_resolution"],
        notes=application["notes"],
        priority=application["is_priority"],
        payment_method=application["payment_method"],
        payment_details=application["payment_details"],
        has_attachments=True,
    )
    telegram_api.edit_message_text(
        ADMIN_CHANNEL_ID, application["admin_channel_message_id"], new_card,
        keyboards.admin_application_actions_keyboard(application["application_code"]),
    )


# ---------------------------------------------------------------------------
# "Reply" button on a support ticket card — DMs the clicking admin to collect
# their reply text (same reasoning as Need More Info above).
# ---------------------------------------------------------------------------
def handle_ticket_reply_button(callback_query: dict, ticket_code: str) -> None:
    admin_id = callback_query["from"]["id"]
    if not is_admin(admin_id):
        telegram_api.answer_callback_query(callback_query["id"], "You are not authorized to do this.", show_alert=True)
        return

    ticket = queries.get_ticket_by_code(ticket_code)
    if not ticket:
        telegram_api.answer_callback_query(callback_query["id"], "Ticket not found.", show_alert=True)
        return

    telegram_api.answer_callback_query(callback_query["id"])
    telegram_api.send_message(admin_id, f"Please type your reply for support ticket {ticket_code}:")
    queries.set_admin_pending_action(admin_id, "awaiting_ticket_reply_text", ticket["id"])


# ---------------------------------------------------------------------------
# Dispatches an admin's free-text DM when they have a pending action queued
# (Need More Info or a ticket Reply). Called from router.py for any private
# message from an admin BEFORE normal command/menu handling, so their answer
# lands in the right place.
# ---------------------------------------------------------------------------
def handle_admin_dm_text(message: dict) -> bool:
    """Returns True if the message was consumed as a pending-action reply."""
    admin_id = message["from"]["id"]
    pending = queries.get_admin_pending_action(admin_id)
    if not pending:
        return False

    text = message.get("text", "").strip()
    if not text:
        return False

    if pending["action"] == "awaiting_more_info_text":
        _handle_more_info_reply(message["chat"]["id"], admin_id, pending["reference_id"], text)
    elif pending["action"] == "awaiting_ticket_reply_text":
        _handle_ticket_reply(message["chat"]["id"], admin_id, pending["reference_id"], text)

    queries.clear_admin_pending_action(admin_id)
    return True


def _handle_more_info_reply(admin_chat_id: int, admin_id: int, application_id: int, admin_message: str) -> None:
    db_application = _get_application_by_id(application_id)
    if not db_application:
        telegram_api.send_message(admin_chat_id, "That application could not be found.")
        return

    code = db_application["application_code"]
    queries.update_application_status(code, "awaiting_user_response", changed_by=admin_id, note=admin_message)

    queries.set_session(db_application["user_id"], fsm.AWAITING_USER_INFO_REPLY, {"application_code": code})
    telegram_api.send_message(
        db_application["user_id"],
        texts.USER_NOTICE_MORE_INFO.format(code=code, message=admin_message),
    )
    telegram_api.send_message(admin_chat_id, f"Your request for more information has been sent to the user regarding {code}.")

    if db_application.get("admin_channel_message_id"):
        refreshed = _get_application_by_id(application_id)
        _refresh_admin_card(refreshed)


def _handle_ticket_reply(admin_chat_id: int, admin_id: int, ticket_id: int, reply_text: str) -> None:
    from db.client import get_client
    res = get_client().table("support_tickets").select("*").eq("id", ticket_id).execute()
    ticket = res.data[0] if res.data else None
    if not ticket:
        telegram_api.send_message(admin_chat_id, "That ticket could not be found.")
        return

    updated = queries.reply_to_ticket(ticket["ticket_code"], reply_text)
    telegram_api.send_message(
        updated["user_id"], texts.SUPPORT_REPLY_TO_USER.format(code=updated["ticket_code"], message=reply_text)
    )
    telegram_api.send_message(admin_chat_id, f"Your reply has been sent to the user for {updated['ticket_code']}.")


def _get_application_by_id(application_id: int) -> dict | None:
    from db.client import get_client
    res = get_client().table("applications").select("*").eq("id", application_id).execute()
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# User's reply to a "Need More Info" request
# ---------------------------------------------------------------------------
def handle_user_info_reply(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    text = message.get("text", "").strip()
    context = session.get("context") or {}
    code = context.get("application_code")

    application = queries.update_application_status(code, "under_review", changed_by=None, note=f"User response: {text}")
    queries.clear_session(telegram_id)
    telegram_api.send_message(chat_id, texts.USER_INFO_REPLY_RECEIVED)

    telegram_api.send_message(
        ADMIN_CHANNEL_ID,
        f"User response received for {code}:\n\n\"{text}\"\n\nStatus reverted to Under Review.",
    )
    _refresh_admin_card(application)


# ---------------------------------------------------------------------------
# Admin text commands (used via DM with the bot)
# ---------------------------------------------------------------------------
def handle_admin_command(message: dict) -> None:
    chat_id = message["chat"]["id"]
    admin_id = message["from"]["id"]
    if not is_admin(admin_id):
        return  # silently ignore — do not reveal that admin commands exist

    text = message.get("text", "").strip()
    parts = text.split(maxsplit=2)
    command = parts[0].lower()

    if command == "/stats":
        stats = queries.get_stats()
        telegram_api.send_message(
            chat_id,
            "Application Statistics\n\n"
            f"Total: {stats['total']}\n"
            f"Pending: {stats['pending']}\n"
            f"Approved: {stats['approved']}\n"
            f"Rejected: {stats['rejected']}\n"
            f"Completed: {stats['completed']}",
        )

    elif command == "/broadcast":
        if len(parts) < 2:
            telegram_api.send_message(chat_id, "Usage: /broadcast <message>")
            return
        broadcast_message = text.split(maxsplit=1)[1]
        user_ids = queries.get_all_verified_user_ids()
        for uid in user_ids:
            telegram_api.send_message(uid, broadcast_message)
        telegram_api.send_message(chat_id, f"Broadcast sent to {len(user_ids)} members.")

    elif command == "/application":
        if len(parts) < 2:
            telegram_api.send_message(chat_id, "Usage: /application <ID>")
            return
        code = parts[1].strip().upper()
        application = queries.get_application_by_code(code)
        if not application:
            telegram_api.send_message(chat_id, "Application not found.")
            return
        telegram_api.send_message(chat_id, texts.application_detail(
            code=application["application_code"], status_label=status_label(application["status"]),
            store_name=application["store_name"], order_number=application["order_number"],
            tracking=application["tracking_numbers"], order_total=application["order_total"],
            resolution=application["desired_resolution"], priority=application["is_priority"],
            updated_at=application["updated_at"],
        ))

    elif command == "/setstatus":
        if len(parts) < 3:
            telegram_api.send_message(chat_id, "Usage: /setstatus <ID> <STATUS>")
            return
        code = parts[1].strip().upper()
        new_status = parts[2].strip().lower().replace(" ", "_")
        valid_statuses = ("pending", "under_review", "awaiting_user_response", "approved",
                           "rejected", "in_progress", "completed")
        if new_status not in valid_statuses:
            telegram_api.send_message(chat_id, f"Invalid status. Valid options: {', '.join(valid_statuses)}")
            return
        try:
            application = queries.update_application_status(code, new_status, changed_by=admin_id)
        except ValueError:
            telegram_api.send_message(chat_id, "Application not found.")
            return
        telegram_api.send_message(chat_id, f"{code} status updated to {status_label(new_status)}.")
        telegram_api.send_message(application["user_id"], f"Your application {code} status has been updated to: {status_label(new_status)}.")
