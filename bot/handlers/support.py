from bot import telegram_api, texts, fsm, keyboards
from bot.config import ADMIN_CHANNEL_ID
from db import queries


def start_support(chat_id: int, telegram_id: int) -> None:
    queries.set_session(telegram_id, fsm.AWAITING_SUPPORT_MESSAGE, {"images": []})
    telegram_api.send_message(chat_id, texts.SUPPORT_PROMPT)


def handle_support_text(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    text = message.get("text", "").strip()
    context = session.get("context") or {}
    context["message"] = text
    queries.set_session(telegram_id, fsm.AWAITING_SUPPORT_IMAGES, context)
    telegram_api.send_message(
        chat_id,
        "You may attach a screenshot now, or type \"done\" to submit your request.",
    )


def handle_support_image(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    context = session.get("context") or {}
    images = context.get("images", [])

    if "photo" in message:
        images.append((message["photo"][-1]["file_id"], "photo"))
    elif "document" in message:
        images.append((message["document"]["file_id"], "document"))

    context["images"] = images
    queries.set_session(telegram_id, fsm.AWAITING_SUPPORT_IMAGES, context)
    telegram_api.send_message(chat_id, "Attachment received. Send another, or type \"done\" to submit.")


def handle_support_images_text(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    text = message.get("text", "").strip().lower()
    if text == "done":
        _finalize_ticket(chat_id, telegram_id, session.get("context") or {})
    else:
        telegram_api.send_message(chat_id, "Type \"done\" when you're finished, or attach another screenshot.")


def _finalize_ticket(chat_id: int, telegram_id: int, context: dict) -> None:
    images = context.get("images", [])
    ticket = queries.create_support_ticket(telegram_id, context.get("message", ""), images)
    queries.clear_session(telegram_id)

    telegram_api.send_message(chat_id, texts.SUPPORT_TICKET_CREATED.format(code=ticket["ticket_code"]))

    from db.client import get_client
    user_res = get_client().table("users").select("*").eq("telegram_id", telegram_id).execute()
    user = user_res.data[0] if user_res.data else {}

    card = texts.admin_support_card(
        code=ticket["ticket_code"], username=user.get("username"), telegram_id=telegram_id,
        message=ticket["message"], has_attachments=bool(images),
    )
    result = telegram_api.send_message(ADMIN_CHANNEL_ID, card, keyboards.admin_ticket_actions_keyboard(ticket["ticket_code"]))
    if result.get("ok"):
        queries.set_ticket_admin_channel_message_id(ticket["ticket_code"], result["result"]["message_id"])

    for file_id, file_type in images:
        if file_type == "photo":
            telegram_api.send_photo(ADMIN_CHANNEL_ID, file_id, caption=ticket["ticket_code"])
        else:
            telegram_api.send_document(ADMIN_CHANNEL_ID, file_id, caption=ticket["ticket_code"])
