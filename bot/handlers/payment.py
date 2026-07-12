from bot import telegram_api, texts, keyboards, fsm
from bot.config import ADMIN_GROUP_ID
from db import queries


def start_payment_collection(chat_id: int, telegram_id: int, application_code: str) -> None:
    queries.set_session(telegram_id, fsm.AWAITING_PAYMENT_METHOD, {"application_code": application_code})
    telegram_api.send_message(chat_id, texts.ASK_PAYMENT_METHOD, keyboards.payment_method_keyboard())


def handle_payment_method_callback(callback_query: dict, method: str) -> None:
    chat_id = callback_query["message"]["chat"]["id"]
    telegram_id = callback_query["from"]["id"]
    telegram_api.answer_callback_query(callback_query["id"])

    session = queries.get_session(telegram_id)
    context = session.get("context") or {}
    context["payment_method"] = method

    if method == "crypto":
        queries.set_session(telegram_id, fsm.AWAITING_CRYPTO_COIN, context)
        telegram_api.send_message(chat_id, texts.ASK_CRYPTO_COIN)
    else:
        queries.set_session(telegram_id, fsm.AWAITING_PAYMENT_HANDLE, context)
        telegram_api.send_message(chat_id, texts.ASK_PAYMENT_HANDLE)


def handle_payment_text(message: dict, session: dict) -> None:
    chat_id = message["chat"]["id"]
    telegram_id = message["from"]["id"]
    text = message.get("text", "").strip()
    state = session["state"]
    context = session.get("context") or {}

    if state == fsm.AWAITING_CRYPTO_COIN:
        context["coin"] = text
        queries.set_session(telegram_id, fsm.AWAITING_CRYPTO_WALLET, context)
        telegram_api.send_message(chat_id, texts.ASK_CRYPTO_WALLET)
        return

    if state == fsm.AWAITING_CRYPTO_WALLET:
        context["wallet"] = text
        _finalize_payment_info(chat_id, telegram_id, context, {"coin": context.get("coin"), "wallet": text})
        return

    if state == fsm.AWAITING_PAYMENT_HANDLE:
        _finalize_payment_info(chat_id, telegram_id, context, {"handle": text})
        return


def _finalize_payment_info(chat_id: int, telegram_id: int, context: dict, details: dict) -> None:
    code = context["application_code"]
    method = context["payment_method"]
    queries.set_payment_info(code, method, details)
    queries.clear_session(telegram_id)

    telegram_api.send_message(chat_id, texts.PAYMENT_INFO_RECEIVED)
    telegram_api.send_message(ADMIN_GROUP_ID, texts.admin_payment_update(code, method, details))
