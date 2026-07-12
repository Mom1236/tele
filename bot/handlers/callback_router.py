"""
Every inline button in the bot funnels through here. Keeping one dispatcher
makes it easy to see every possible callback_data value in one place.
"""
from bot import telegram_api
from bot.middleware import enforce_button_rate_limit
from bot.handlers import start, application, admin, payment


def route_callback_query(callback_query: dict) -> None:
    data = callback_query["data"]
    telegram_id = callback_query["from"]["id"]

    if not enforce_button_rate_limit(telegram_id, callback_query["id"]):
        return

    if data == "verify_membership":
        start.handle_verify_membership_callback(callback_query)
        return

    # Everything past this point requires verified membership.
    from db import queries
    if not queries.is_user_verified(telegram_id):
        telegram_api.answer_callback_query(callback_query["id"], "Please verify your membership first.", show_alert=True)
        return

    chat_id = callback_query["message"]["chat"]["id"]

    if data == "menu_new_application":
        telegram_api.answer_callback_query(callback_query["id"])
        application.start_new_application(chat_id, telegram_id)

    elif data == "menu_check_status":
        telegram_api.answer_callback_query(callback_query["id"])
        application.show_my_applications(chat_id, telegram_id)

    elif data == "menu_my_applications":
        telegram_api.answer_callback_query(callback_query["id"])
        application.show_my_applications(chat_id, telegram_id)

    elif data == "menu_support":
        telegram_api.answer_callback_query(callback_query["id"])
        from bot.handlers.support import start_support
        start_support(chat_id, telegram_id)

    elif data.startswith("view_app_"):
        telegram_api.answer_callback_query(callback_query["id"])
        code = data.removeprefix("view_app_")
        application.show_application_detail(chat_id, code)

    elif data == "draft_continue":
        telegram_api.answer_callback_query(callback_query["id"])
        application.resume_draft(chat_id, telegram_id)

    elif data == "draft_restart":
        telegram_api.answer_callback_query(callback_query["id"])
        application.restart_draft(chat_id, telegram_id)

    elif data in ("priority_yes", "priority_no"):
        application.handle_priority_callback(callback_query, data.endswith("_yes"))

    elif data == "images_done":
        application.handle_images_done_callback(callback_query)

    elif data == "images_skip":
        application.handle_images_skip_callback(callback_query)

    elif data.startswith("pay_"):
        payment.handle_payment_method_callback(callback_query, data.removeprefix("pay_"))

    elif data.startswith("admin_"):
        # admin_<action>_<code>  e.g. admin_approve_CIH-000123
        remainder = data.removeprefix("admin_")
        action, code = remainder.split("_", 1)
        admin.handle_admin_application_action(callback_query, action, code)

    else:
        telegram_api.answer_callback_query(callback_query["id"])
