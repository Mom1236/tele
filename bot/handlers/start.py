from bot import telegram_api, texts, keyboards
from bot.middleware import check_membership_live
from db import queries


def handle_start(message: dict) -> None:
    chat_id = message["chat"]["id"]
    user = message["from"]
    telegram_id = user["id"]

    queries.get_or_create_user(telegram_id, user.get("username"), user.get("first_name"))

    if check_membership_live(telegram_id):
        queries.set_user_verified(telegram_id, True)
        _show_main_menu_or_resume(chat_id, telegram_id)
    else:
        queries.set_user_verified(telegram_id, False)
        telegram_api.send_message(chat_id, texts.NOT_A_MEMBER, keyboards.verification_keyboard())


def handle_verify_membership_callback(callback_query: dict) -> None:
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    telegram_id = callback_query["from"]["id"]

    if check_membership_live(telegram_id):
        queries.set_user_verified(telegram_id, True)
        telegram_api.edit_message_text(chat_id, message_id, texts.VERIFICATION_SUCCESS)
        _show_main_menu_or_resume(chat_id, telegram_id)
    else:
        telegram_api.answer_callback_query(callback_query["id"], texts.VERIFICATION_FAILED, show_alert=True)


def _show_main_menu_or_resume(chat_id: int, telegram_id: int) -> None:
    session = queries.get_session(telegram_id)
    if session["state"] not in ("idle",) and session["state"].startswith("app_"):
        telegram_api.send_message(chat_id, texts.DRAFT_RESUME_PROMPT, keyboards.draft_resume_keyboard())
        return
    telegram_api.send_message(chat_id, texts.WELCOME_BACK, keyboards.main_menu_keyboard())


def show_main_menu(chat_id: int) -> None:
    telegram_api.send_message(chat_id, texts.WELCOME_BACK, keyboards.main_menu_keyboard())
