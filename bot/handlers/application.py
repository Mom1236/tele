from bot import telegram_api, texts, keyboards, fsm
from bot.config import ADMIN_CHANNEL_ID, MAX_ACTIVE_APPLICATIONS, MAX_IMAGES_PER_APPLICATION
from bot.utils import status_label, format_timestamp
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
    queries.set_session(telegram_id, fsm.APP_STORE_NAME, {"images": []})
    telegram_api.send_message(chat_id, texts.ASK_STORE_NAME)


def resume_draft(chat_id: int, telegram_id: int) -> None:
    session = queries.get_session(telegram_id)
    prompt = _prompt_for_state(session["state"])
    if prompt:
        telegram_api.send_message(chat_id, prompt)
    else:
        from bot.handlers.start import show_main_menu
        show_main_menu(chat_id)


def restart_draft(chat_id: int, telegram_id: int) -> None:
    queries.clear_session(telegram_id)
    start_new_application(chat_id, telegram_id)


def _prompt_for_state(state: str) -> str | None:
    return {
        fsm.APP_STORE_NAME: texts.ASK_STORE_NAME,
        fsm.APP_ORDER_NUMBER: texts.ASK_ORDER_NUMBER,
        fsm.APP_ACCOUNT_EMAIL: texts.ASK_ACCOUNT_EMAIL,
        fsm.APP_VERIFICATION_CODE: texts.ASK_VERIFICATION_CODE,
        fsm.APP_ORDER_TOTAL: texts.ASK_ORDER_TOTAL,
        fsm.APP_TRACKING: texts.ASK_TRACKING,
        fsm.APP_ORDER_STATUS: texts.ASK_ORDER_STATUS,
        fsm.APP_DESIRED_RESOLUTION: texts.ASK_DESIRED_RESOLUTION,
        fsm.APP_NOTES: texts.ASK_NOTES,
        fsm.APP_PRIORITY: texts.ASK_PRIORITY,
        fsm.APP_PAYMENT_METHOD: texts.ASK_PAYMENT_METHOD,
        fsm.APP_CRYPTO_COIN: texts.ASK_CRYPTO_COIN,
        fsm.APP_CRYPTO_WALLET: texts.ASK_CRYPTO_WALLET,
        fsm.APP_PAYMENT_HANDLE: texts.ASK_PAYMENT_HANDLE,
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

    if state == fsm.APP_STORE_NAME:
        context["store_name"] = text
        queries.set_session(telegram_id, fsm.APP_ORDER_NUMBER, context)
        telegram_api.send_message(chat_id, texts.ASK_ORDER_NUMBER)

    elif state == fsm.APP_ORDER_NUMBER:
        context["order_number"] = text
        queries.set_session(telegram_id, fsm.APP_ACCOUNT_EMAIL, context)
        telegram_api.send_message(chat_id, texts.ASK_ACCOUNT_EMAIL)

    elif state == fsm.APP_ACCOUNT_EMAIL:
        context["account_email"] = text
        queries.set_session(telegram_id, fsm.APP_VERIFICATION_CODE, context)
        telegram_api.send_message(chat_id, texts.ASK_VERIFICATION_CODE)

    elif state == fsm.APP_VERIFICATION_CODE:
        context["verification_code"] = text
        queries.set_session(telegram_id, fsm.APP_ORDER_TOTAL, context)
        telegram_api.send_message(chat_id, texts.ASK_ORDER_TOTAL)

    elif state == fsm.APP_ORDER_TOTAL:
        context["order_total"] = text
        queries.set_session(telegram_id, fsm.APP_TRACKING, context)
        telegram_api.send_message(chat_id, texts.ASK_TRACKING)

    elif state == fsm.APP_TRACKING:
        context["tracking"] = text
        queries.set_session(telegram_id, fsm.APP_ORDER_STATUS, context)
        telegram_api.send_message(chat_id, texts.ASK_ORDER_STATUS)

    elif state == fsm.APP_ORDER_STATUS:
        context["order_status"] = text
        queries.set_session(telegram_id, fsm.APP_DESIRED_RESOLUTION, context)
        telegram_api.send_message(chat_id, texts.ASK_DESIRED_RESOLUTION)

    elif state == fsm.APP_DESIRED_RESOLUTION:
        context["desired_resolution"] = text
        queries.set_session(telegram_id, fsm.APP_NOTES, context)
        telegram_api.send_message(chat_id, texts.ASK_NOTES)

    elif state == fsm.APP_NOTES:
        context["notes"] = "" if text.lower() == "none" else text
        queries.set_session(telegram_id, fsm.APP_PRIORITY, context)
        telegram_api.send_message(chat_id, texts.ASK_PRIORITY, keyboards.yes_no_keyboard("priority"))

    elif state == fsm.APP_CRYPTO_COIN:
        context["coin"] = text
        queries.set_session(telegram_id, fsm.APP_CRYPTO_WALLET, context)
        telegram_api.send_message(chat_id, texts.ASK_CRYPTO_WALLET)

    elif state == fsm.APP_CRYPTO_WALLET:
        context["wallet"] = text
        queries.set_session(telegram_id, fsm.APP_IMAGES, context)
        telegram_api.send_message(chat_id, texts.ASK_IMAGES, keyboards.images_step_keyboard(0))

    elif state == fsm.APP_PAYMENT_HANDLE:
        context["handle"] = text
        queries.set_session(telegram_id, fsm.APP_IMAGES, context)
        telegram_api.send_message(chat_id, texts.ASK_IMAGES, keyboards.images_step_keyboard(0))

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
    queries.set_session(telegram_id, fsm.APP_PAYMENT_METHOD, context)
    telegram_api.answer_callback_query(callback_query["id"])
    telegram_api.send_message(chat_id, texts.ASK_PAYMENT_METHOD, keyboards.payment_method_keyboard())


# ---------------------------------------------------------------------------
# Payment method (for the service fee) callback
# ---------------------------------------------------------------------------
def handle_payment_method_callback(callback_query: dict, method: str) -> None:
    chat_id = callback_query["message"]["chat"]["id"]
    telegram_id = callback_query["from"]["id"]
    telegram_api.answer_callback_query(callback_query["id"])

    session = queries.get_session(telegram_id)
    context = session.get("context") or {}
    context["payment_method"] = method

    if method == "crypto":
        queries.set_session(telegram_id, fsm.APP_CRYPTO_COIN, context)
        telegram_api.send_message(chat_id, texts.ASK_CRYPTO_COIN)
    else:
        queries.set_session(telegram_id, fsm.APP_PAYMENT_HANDLE, context)
        telegram_api.send_message(chat_id, texts.ASK_PAYMENT_HANDLE)


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
# Finalize + submit to admin channel
# ---------------------------------------------------------------------------
def _finalize_application(chat_id: int, telegram_id: int, context: dict) -> None:
    images = context.get("images", [])
    method = context.get("payment_method")
    if method == "crypto":
        payment_details = {"coin": context.get("coin"), "wallet": context.get("wallet")}
    else:
        payment_details = {"handle": context.get("handle")}

    application = queries.create_application(
        user_id=telegram_id,
        store_name=context.get("store_name", ""),
        order_number=context.get("order_number", ""),
        account_email=context.get("account_email", ""),
        verification_code=context.get("verification_code", ""),
        order_total=context.get("order_total", ""),
        tracking=context.get("tracking", ""),
        order_status=context.get("order_status", ""),
        desired_resolution=context.get("desired_resolution", ""),
        notes=context.get("notes", ""),
        is_priority=bool(context.get("priority", False)),
        payment_method=method,
        payment_details=payment_details,
        image_file_ids=images,
    )
    queries.clear_session(telegram_id)

    telegram_api.send_message(chat_id, texts.APPLICATION_SUBMITTED.format(code=application["application_code"]))
    from bot.handlers.start import show_main_menu
    show_main_menu(chat_id)

    _post_to_admin_channel(application, images)


def _post_to_admin_channel(application: dict, images: list) -> None:
    from db.client import get_client
    user_res = get_client().table("users").select("*").eq("telegram_id", application["user_id"]).execute()
    user = user_res.data[0] if user_res.data else {}

    card_text = texts.admin_application_card(
        code=application["application_code"],
        username=user.get("username"),
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
        has_attachments=bool(images),
    )

    result = telegram_api.send_message(
        ADMIN_CHANNEL_ID, card_text, keyboards.admin_application_actions_keyboard(application["application_code"])
    )
    if result.get("ok"):
        message_id = result["result"]["message_id"]
        queries.set_admin_channel_message_id(application["application_code"], message_id)
        # Priority requests get pinned so they're impossible for admins to miss.
        if application["is_priority"]:
            telegram_api.pin_chat_message(ADMIN_CHANNEL_ID, message_id, disable_notification=False)

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
        store_name=app["store_name"],
        order_number=app["order_number"],
        tracking=app["tracking_numbers"],
        order_total=app["order_total"],
        resolution=app["desired_resolution"],
        priority=app["is_priority"],
        updated_at=format_timestamp(app["updated_at"]),
    ))
