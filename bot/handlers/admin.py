from bot import telegram_api, texts, keyboards, fsm
from bot.config import ADMIN_GROUP_ID, ADMIN_IDS
from bot.utils import status_label
from db import queries
from bot.handlers.payment import start_payment_collection


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
        start_payment_collection(application["user_id"], application["user_id"], code)

    elif action == "reject":
        _set_status_and_refresh(application, "rejected", admin_id)
        telegram_api.send_message(application["user_id"], texts.USER_NOTICE_REJECTED)

    elif action == "complete":
        _set_status_and_refresh(application, "completed", admin_id)
        telegram_api.send_message(application["user_id"], texts.USER_NOTICE_COMPLETED)

    elif action == "moreinfo":
        prompt_text = texts.ASK_ADMIN_MORE_INFO_TEXT.format(code=code)
        result = telegram_api.send_message(ADMIN_GROUP_ID, prompt_text)
        if result.get("ok"):
            queries.set_admin_pending_action(
                result["result"]["message_id"], "awaiting_more_info_text", application["id"]
            )


def _set_status_and_refresh(application: dict, new_status: str, admin_id: int) -> None:
    updated = queries.update_application_status(application["application_code"], new_status, changed_by=admin_id)
    if application.get("admin_channel_message_id"):
        from db.client import get_client
        user_res = get_client().table("users").select("username").eq("telegram_id", updated["user_id"]).execute()
        username = user_res.data[0]["username"] if user_res.data else None
        new_card = texts.admin_application_card(
            code=updated["application_code"],
            username=username,
            telegram_id=updated["user_id"],
            status_label=status_label(updated["status"]),
            courier=updated["courier"],
            tracking=updated["tracking_numbers"],
            amount=updated["amount"],
            priority=updated["is_priority"],
            notes=updated["notes"],
            has_attachments=True,
        )
        telegram_api.edit_message_text(
            ADMIN_GROUP_ID, application["admin_channel_message_id"], new_card,
            keyboards.admin_application_actions_keyboard(updated["application_code"]),
        )


# ---------------------------------------------------------------------------
# Admin replies in the group — routed here from the router when a message in
# ADMIN_GROUP_ID is a reply to a tracked prompt or ticket card.
# ---------------------------------------------------------------------------
def handle_admin_reply_to_more_info_prompt(message: dict, pending_action: dict) -> None:
    admin_message = message.get("text", "").strip()
    application_id = pending_action["application_id"]

    db_application = _get_application_by_id(application_id)
    if not db_application:
        return

    code = db_application["application_code"]
    queries.update_application_status(code, "awaiting_user_response", changed_by=message["from"]["id"], note=admin_message)
    queries.clear_admin_pending_action(pending_action["prompt_message_id"])

    queries.set_session(db_application["user_id"], fsm.AWAITING_USER_INFO_REPLY, {"application_code": code})
    telegram_api.send_message(
        db_application["user_id"],
        texts.USER_NOTICE_MORE_INFO.format(code=code, message=admin_message),
    )
    telegram_api.send_message(message["chat"]["id"], f"Your request for more information has been sent to the user regarding {code}.")


def handle_admin_reply_to_ticket(message: dict, ticket: dict) -> None:
    reply_text = message.get("text", "").strip()
    updated = queries.reply_to_ticket(ticket["ticket_code"], reply_text)
    telegram_api.send_message(
        updated["user_id"], texts.SUPPORT_REPLY_TO_USER.format(code=updated["ticket_code"], message=reply_text)
    )
    telegram_api.send_message(message["chat"]["id"], f"Your reply has been sent to the user for {updated['ticket_code']}.")


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

    queries.update_application_status(code, "under_review", changed_by=None, note=f"User response: {text}")
    queries.clear_session(telegram_id)
    telegram_api.send_message(chat_id, texts.USER_INFO_REPLY_RECEIVED)

    application = queries.get_application_by_code(code)
    telegram_api.send_message(
        ADMIN_GROUP_ID,
        f"User response received for {code}:\n\n\"{text}\"\n\nStatus reverted to Under Review.",
    )
    if application and application.get("admin_channel_message_id"):
        _set_status_and_refresh(application, "under_review", admin_id=None)


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
            courier=application["courier"], tracking=application["tracking_numbers"],
            amount=application["amount"], priority=application["is_priority"],
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
