"""
Builders for Telegram inline keyboards. Kept separate from handlers so the
visual layer can change without touching business logic.
"""
from bot.config import PRIVATE_CHANNEL_INVITE_LINK


def verification_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Join Channel", "url": PRIVATE_CHANNEL_INVITE_LINK}],
            [{"text": "I've Joined", "callback_data": "verify_membership"}],
        ]
    }


def main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Submit New Application", "callback_data": "menu_new_application"}],
            [{"text": "Check Application Status", "callback_data": "menu_check_status"}],
            [{"text": "My Applications", "callback_data": "menu_my_applications"}],
            [{"text": "Support", "callback_data": "menu_support"}],
        ]
    }


def yes_no_keyboard(prefix: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Yes", "callback_data": f"{prefix}_yes"},
                {"text": "No", "callback_data": f"{prefix}_no"},
            ]
        ]
    }


def images_step_keyboard(count: int) -> dict:
    row = [{"text": "Done", "callback_data": "images_done"}]
    if count == 0:
        row.append({"text": "Skip", "callback_data": "images_skip"})
    return {"inline_keyboard": [row]}


def draft_resume_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Continue Application", "callback_data": "draft_continue"},
                {"text": "Restart Application", "callback_data": "draft_restart"},
            ]
        ]
    }


def admin_application_actions_keyboard(code: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"admin_approve_{code}"},
                {"text": "Need More Info", "callback_data": f"admin_moreinfo_{code}"},
            ],
            [
                {"text": "Reject", "callback_data": f"admin_reject_{code}"},
                {"text": "Mark Complete", "callback_data": f"admin_complete_{code}"},
            ],
        ]
    }


def payment_method_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Cash App", "callback_data": "pay_cashapp"}],
            [{"text": "PayPal", "callback_data": "pay_paypal"}],
            [{"text": "Zelle", "callback_data": "pay_zelle"}],
            [{"text": "Crypto", "callback_data": "pay_crypto"}],
        ]
    }


def my_applications_keyboard(applications: list[dict]) -> dict:
    rows = []
    for app in applications:
        label = f"{app['application_code']} — {app['status_label']}"
        rows.append([{"text": label, "callback_data": f"view_app_{app['application_code']}"}])
    return {"inline_keyboard": rows} if rows else {"inline_keyboard": []}
