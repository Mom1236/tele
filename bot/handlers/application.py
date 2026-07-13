from bot import telegram_api, texts, keyboards, fsm
from bot.config import ADMIN_CHANNEL_ID, MAX_ACTIVE_APPLICATIONS, MAX_IMAGES_PER_APPLICATION
from bot.utils import is_valid_amount, status_label, format_timestamp
from db import queries


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def start_new_application(chat_id: int, telegram_id: int) -> None:
    if queries.has_reached_active_limit(telegram_id):
        telegram_api.send_message(
            chat_id, texts.MAX_ACTIVE_APPLICATIONS_REACHED.format(max=MAX_ACTIVE_APPLICATIONS)
        )
        return

    if not queries.check_new_application_cooldown(telegram_id):
        telegram_api.send_message(chat_id, texts.RATE_LIMITED)
        return

    queries.record_new_application_attempt(telegram_id)
    queries.set_session(telegram_id, fsm.APP_COURIER, {"images": []})
    telegram_api.send_message(chat_id, texts.ASK_COURIER)


def resume_draft(chat_id: int, telegram_id: int) -> None:
    session = queries.get_session(telegram_id)
    prompt = _prompt_for_state(session["state"])
    if prompt:
        telegram_api.send_message(chat_id, prompt)
    else:
        # Somehow no draft in progress after all — send them to the menu.
        from bot.handlers.start import show_main_menu
        show_main_menu(chat_id)


def restart_draft(chat_id: int, telegram_id: int) -> None:
    queries.clear_session(telegram_id)
    start_new_application(chat_id, telegram_id)


def _prompt_for_state(state: str) -> str | None:
    return {
        fsm.APP_COURIER: texts.ASK_COURIER,
        fsm.APP_TRACKING: texts.ASK_TRACKING,
        fsm.APP_AMOUNT: texts.ASK_AMOUNT,
        fsm.APP_NOTES: texts.ASK_NOTES,
        fsm.APP_PRIORITY: texts.ASK_PRIORITY,
        fsm.APP_IMAGES: texts.ASK_IMAGES,
    }.get(state)


# ---------------------------------------------------------------------------
# Text message handling while inside the form
# ---------------------------------------------------------------------------
def handle_form_text(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    text = message.get("text", "").strip()
    state = session["state"]
    context = session.get("context") or {}

    if state == fsm.APP_COURIER:
        context["courier"] = text
        queries.set_session(telegram_id, fsm.APP_TRACKING, context)
        telegram_api.send_message(chat_id, texts.ASK_TRACKING)

    elif state == fsm.APP_TRACKING:
        context["tracking"] = text
        queries.set_session(telegram_id, fsm.APP_AMOUNT, context)
        telegram_api.send_message(chat_id, texts.ASK_AMOUNT)

    elif state == fsm.APP_AMOUNT:
        if not is_valid_amount(text):
            telegram_api.send_message(chat_id, "Please enter a valid amount (e.g. $1,250.00).")
            return
        context["amount"] = text
        queries.set_session(telegram_id, fsm.APP_NOTES, context)
        telegram_api.send_message(chat_id, texts.ASK_NOTES)

    elif state == fsm.APP_NOTES:
        context["notes"] = "" if text.lower() == "none" else text
        queries.set_session(telegram_id, fsm.APP_PRIORITY, context)
        telegram_api.send_message(chat_id, texts.ASK_PRIORITY, keyboards.yes_no_keyboard("priority"))

    elif state == fsm.APP_IMAGES:
        # Free text while in the images step is treated as a no-op nudge.
        telegram_api.send_message(chat_id, texts.ASK_IMAGES, keyboards.images_step_keyboard(len(context.get("images", []))))


# ---------------------------------------------------------------------------
# Priority Yes/No callback
# ---------------------------------------------------------------------------
def handle_priority_callback(callback_query: dict, choice: bool) -> None:
    chat_id = callback_query["message"]["chat"]["id"]
    telegram_id = callback_query["from"]["id"]
    session = queries.get_session(telegram_id)
    context = session.get("context") or {}
    context["priority"] = choice
    queries.set_session(telegram_id, fsm.APP_IMAGES, context)
    telegram_api.answer_callback_query(callback_query["id"])
    telegram_api.send_message(chat_id, texts.ASK_IMAGES, keyboards.images_step_keyboard(0))


# ---------------------------------------------------------------------------
# Image collection
# ---------------------------------------------------------------------------
def handle_form_image(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    context = session.get("context") or {}
    images = context.get("images", [])

    if len(images) >= MAX_IMAGES_PER_APPLICATION:
        telegram_api.send_message(chat_id, texts.IMAGE_LIMIT_REACHED.format(max=MAX_IMAGES_PER_APPLICATION))
        _finalize_application(chat_id, telegram_id, context)
        return

    if "photo" in message:
        file_id = message["photo"][-1]["file_id"]  # largest resolution
        images.append((file_id, "photo"))
    elif "document" in message:
        file_id = message["document"]["file_id"]
        images.append((file_id, "document"))
    else:
        return

    context["images"] = images
    queries.set_session(telegram_id, fsm.APP_IMAGES, context)

    if len(images) >= MAX_IMAGES_PER_APPLICATION:
        telegram_api.send_message(chat_id, texts.IMAGE_LIMIT_REACHED.format(max=MAX_IMAGES_PER_APPLICATION))
        _finalize_application(chat_id, telegram_id, context)
    else:
        telegram_api.send_message(
            chat_id,
            texts.IMAGE_RECEIVED.format(count=len(images), max=MAX_IMAGES_PER_APPLICATION),
            keyboards.images_step_keyboard(len(images)),
        )


def handle_images_done_callback(callback_query: dict) -> None:
    chat_id = callback_query["message"]["chat"]["id"]
    telegram_id = callback_query["from"]["id"]
    telegram_api.answer_callback_query(callback_query["id"])
    session = queries.get_session(telegram_id)
    context = session.get("context") or {}
    _finalize_application(chat_id, telegram_id, context)


def handle_images_skip_callback(callback_query: dict) -> None:
    handle_images_done_callback(callback_query)


# ---------------------------------------------------------------------------
# Finalize + submit to admin group
# ---------------------------------------------------------------------------
def _finalize_application(chat_id: int, telegram_id: int, context: dict) -> None:
    images = context.get("images", [])
    application = queries.create_application(
        user_id=telegram_id,
        courier=context.get("courier", ""),
        tracking=context.get("tracking", ""),
        amount=context.get("amount", ""),
        notes=context.get("notes", ""),
        is_priority=bool(context.get("priority", False)),
        image_file_ids=images,
    )
    queries.clear_session(telegram_id)

    telegram_api.send_message(chat_id, texts.APPLICATION_SUBMITTED.format(code=application["application_code"]))
    from bot.handlers.start import show_main_menu
    show_main_menu(chat_id)

    _post_to_admin_group(application, images)


def _post_to_admin_group(application: dict, images: list) -> None:
    from db.client import get_client
    user_res = get_client().table("users").select("*").eq("telegram_id", application["user_id"]).execute()
    user = user_res.data[0] if user_res.data else {}

    card_text = texts.admin_application_card(
        code=application["application_code"],
        username=user.get("username"),
        telegram_id=application["user_id"],
        status_label=status_label(application["status"]),
        courier=application["courier"],
        tracking=application["tracking_numbers"],
        amount=application["amount"],
        priority=application["is_priority"],
        notes=application["notes"],
        has_attachments=bool(images),
    )

    result = telegram_api.send_message(
        ADMIN_CHANNEL_ID, card_text, keyboards.admin_application_actions_keyboard(application["application_code"])
    )
    if result.get("ok"):
        queries.set_admin_channel_message_id(application["application_code"], result["result"]["message_id"])

    # Send attachments as a follow-up album-style burst so the card stays clean.
    for file_id, file_type in images:
        if file_type == "photo":
            telegram_api.send_photo(ADMIN_CHANNEL_ID, file_id, caption=application["application_code"])
        else:
            telegram_api.send_document(ADMIN_CHANNEL_ID, file_id, caption=application["application_code"])


# ---------------------------------------------------------------------------
# Status / My Applications
# ---------------------------------------------------------------------------
def show_check_status_prompt(chat_id: int) -> None:
    telegram_api.send_message(chat_id, "Please select an application from 'My Applications' to view its status, "
                                        "or contact Support for assistance.")


def show_my_applications(chat_id: int, telegram_id: int) -> None:
    apps = queries.get_user_applications(telegram_id)
    if not apps:
        telegram_api.send_message(chat_id, texts.NO_APPLICATIONS_YET)
        return
    formatted = [{"application_code": a["application_code"], "status_label": status_label(a["status"])} for a in apps]
    telegram_api.send_message(chat_id, "Your Applications:", keyboards.my_applications_keyboard(formatted))


def show_application_detail(chat_id: int, code: str) -> None:
    app = queries.get_application_by_code(code)
    if not app:
        telegram_api.send_message(chat_id, "That application could not be found.")
        return
    telegram_api.send_message(chat_id, texts.application_detail(
        code=app["application_code"],
        status_label=status_label(app["status"]),
        courier=app["courier"],
        tracking=app["tracking_numbers"],
        amount=app["amount"],
        priority=app["is_priority"],
        updated_at=format_timestamp(app["updated_at"]),
    ))
