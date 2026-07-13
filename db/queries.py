"""
All Supabase reads/writes live here. Handlers never talk to the DB client
directly — this keeps business logic and data access cleanly separated.
"""
import datetime
from db.client import get_client
from bot.fsm import PRIORITY_FEE_AMOUNT
from bot.config import (
    NEW_APPLICATION_COOLDOWN_SECONDS,
    MAX_BUTTON_PRESSES_PER_WINDOW, BUTTON_WINDOW_SECONDS,
    MAX_FORM_MESSAGES_PER_WINDOW, FORM_MESSAGE_WINDOW_SECONDS,
    MAX_ACTIVE_APPLICATIONS,
)

ACTIVE_STATUSES = ("pending", "under_review", "awaiting_user_response", "approved", "in_progress")


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------
def get_or_create_user(telegram_id: int, username: str | None, first_name: str | None) -> dict:
    db = get_client()
    existing = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
    now = datetime.datetime.utcnow().isoformat()
    if existing.data:
        db.table("users").update({
            "username": username, "first_name": first_name, "last_active_at": now
        }).eq("telegram_id", telegram_id).execute()
        return existing.data[0]
    result = db.table("users").insert({
        "telegram_id": telegram_id, "username": username, "first_name": first_name,
        "last_active_at": now,
    }).execute()
    return result.data[0]


def set_user_verified(telegram_id: int, verified: bool = True) -> None:
    get_client().table("users").update({"is_verified": verified}).eq("telegram_id", telegram_id).execute()


def is_user_verified(telegram_id: int) -> bool:
    res = get_client().table("users").select("is_verified").eq("telegram_id", telegram_id).execute()
    return bool(res.data and res.data[0]["is_verified"])


# ---------------------------------------------------------------------------
# SESSIONS (FSM state)
# ---------------------------------------------------------------------------
def get_session(telegram_id: int) -> dict:
    db = get_client()
    res = db.table("sessions").select("*").eq("telegram_id", telegram_id).execute()
    if res.data:
        return res.data[0]
    created = db.table("sessions").insert({"telegram_id": telegram_id, "state": "idle", "context": {}}).execute()
    return created.data[0]


def set_session(telegram_id: int, state: str, context: dict | None = None) -> None:
    db = get_client()
    payload = {"state": state, "updated_at": datetime.datetime.utcnow().isoformat()}
    if context is not None:
        payload["context"] = context
    db.table("sessions").update(payload).eq("telegram_id", telegram_id).execute()


def clear_session(telegram_id: int) -> None:
    set_session(telegram_id, "idle", {})


# ---------------------------------------------------------------------------
# RATE LIMITING
# ---------------------------------------------------------------------------
def _record_event(telegram_id: int, action: str) -> None:
    get_client().table("rate_events").insert({"telegram_id": telegram_id, "action": action}).execute()


def _count_recent_events(telegram_id: int, action: str, window_seconds: int) -> int:
    db = get_client()
    since = (datetime.datetime.utcnow() - datetime.timedelta(seconds=window_seconds)).isoformat()
    res = (db.table("rate_events").select("id", count="exact")
           .eq("telegram_id", telegram_id).eq("action", action).gte("created_at", since).execute())
    return res.count or 0


def check_and_record_button_press(telegram_id: int) -> bool:
    """Returns True if allowed, False if rate-limited."""
    count = _count_recent_events(telegram_id, "button", BUTTON_WINDOW_SECONDS)
    if count >= MAX_BUTTON_PRESSES_PER_WINDOW:
        return False
    _record_event(telegram_id, "button")
    return True


def check_and_record_form_message(telegram_id: int) -> bool:
    count = _count_recent_events(telegram_id, "form_message", FORM_MESSAGE_WINDOW_SECONDS)
    if count >= MAX_FORM_MESSAGES_PER_WINDOW:
        return False
    _record_event(telegram_id, "form_message")
    return True


def check_new_application_cooldown(telegram_id: int) -> bool:
    count = _count_recent_events(telegram_id, "new_application", NEW_APPLICATION_COOLDOWN_SECONDS)
    return count == 0


def record_new_application_attempt(telegram_id: int) -> None:
    _record_event(telegram_id, "new_application")


# ---------------------------------------------------------------------------
# APPLICATIONS
# ---------------------------------------------------------------------------
def count_active_applications(telegram_id: int) -> int:
    db = get_client()
    res = (db.table("applications").select("id", count="exact")
           .eq("user_id", telegram_id).in_("status", ACTIVE_STATUSES).execute())
    return res.count or 0


def has_reached_active_limit(telegram_id: int) -> bool:
    return count_active_applications(telegram_id) >= MAX_ACTIVE_APPLICATIONS


def _generate_application_code() -> str:
    db = get_client()
    # nextval on a dedicated sequence guarantees no collisions under concurrency
    res = db.rpc("nextval_application_code").execute()
    n = res.data
    return f"CIH-{int(n):06d}"


def create_application(user_id: int, store_name: str, order_number: str, account_email: str,
                        verification_code: str, order_total: str, tracking: str, order_status: str,
                        desired_resolution: str, notes: str, is_priority: bool,
                        payment_method: str, payment_details: dict,
                        image_file_ids: list[tuple[str, str]]) -> dict:
    db = get_client()
    code = _generate_application_code()
    result = db.table("applications").insert({
        "application_code": code,
        "user_id": user_id,
        "status": "pending",
        "store_name": store_name,
        "order_number": order_number,
        "account_email": account_email,
        "verification_code": verification_code,
        "order_total": order_total,
        "tracking_numbers": tracking,
        "order_status": order_status,
        "desired_resolution": desired_resolution,
        "notes": notes,
        "is_priority": is_priority,
        "priority_fee": PRIORITY_FEE_AMOUNT if is_priority else None,
        "payment_method": payment_method,
        "payment_details": payment_details,
    }).execute()
    application = result.data[0]

    for file_id, file_type in image_file_ids:
        db.table("application_images").insert({
            "application_id": application["id"], "file_id": file_id, "file_type": file_type,
        }).execute()

    db.table("application_status_history").insert({
        "application_id": application["id"], "old_status": None, "new_status": "pending",
    }).execute()

    return application


def get_application_by_code(code: str) -> dict | None:
    db = get_client()
    res = db.table("applications").select("*").eq("application_code", code).execute()
    return res.data[0] if res.data else None


def get_application_images(application_id: int) -> list[dict]:
    db = get_client()
    res = db.table("application_images").select("*").eq("application_id", application_id).execute()
    return res.data


def get_user_applications(telegram_id: int) -> list[dict]:
    db = get_client()
    res = (db.table("applications").select("*").eq("user_id", telegram_id)
           .order("created_at", desc=True).execute())
    return res.data


def set_admin_channel_message_id(code: str, message_id: int) -> None:
    get_client().table("applications").update(
        {"admin_channel_message_id": message_id}
    ).eq("application_code", code).execute()


def update_application_status(code: str, new_status: str, changed_by: int | None = None,
                               note: str | None = None) -> dict:
    db = get_client()
    application = get_application_by_code(code)
    if not application:
        raise ValueError(f"Application {code} not found")

    db.table("applications").update({
        "status": new_status, "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("application_code", code).execute()

    db.table("application_status_history").insert({
        "application_id": application["id"],
        "old_status": application["status"],
        "new_status": new_status,
        "changed_by": changed_by,
        "note": note,
    }).execute()

    return get_application_by_code(code)


def get_stats() -> dict:
    db = get_client()
    def count(status=None):
        q = db.table("applications").select("id", count="exact")
        if status:
            q = q.eq("status", status)
        return q.execute().count or 0

    return {
        "total": count(),
        "pending": count("pending") + count("under_review"),
        "approved": count("approved"),
        "rejected": count("rejected"),
        "completed": count("completed"),
    }


def get_all_verified_user_ids() -> list[int]:
    db = get_client()
    res = db.table("users").select("telegram_id").eq("is_verified", True).execute()
    return [row["telegram_id"] for row in res.data]


# ---------------------------------------------------------------------------
# ADMIN PENDING ACTIONS — DM-based follow-ups
# Keyed by the admin's own Telegram ID. Used when an admin clicks a button
# that requires them to type a free-text response (Need More Info, ticket
# Reply) — since the admin channel is a broadcast channel, the bot can't
# attribute an in-channel message to a specific admin, so this happens via
# a private DM with that admin instead.
# ---------------------------------------------------------------------------
def set_admin_pending_action(admin_id: int, action: str, reference_id: int) -> None:
    db = get_client()
    db.table("admin_pending_actions").upsert({
        "admin_telegram_id": admin_id, "action": action, "reference_id": reference_id,
    }).execute()


def get_admin_pending_action(admin_id: int) -> dict | None:
    db = get_client()
    res = db.table("admin_pending_actions").select("*").eq("admin_telegram_id", admin_id).execute()
    return res.data[0] if res.data else None


def clear_admin_pending_action(admin_id: int) -> None:
    get_client().table("admin_pending_actions").delete().eq("admin_telegram_id", admin_id).execute()


# ---------------------------------------------------------------------------
# SUPPORT TICKETS
# ---------------------------------------------------------------------------
def _generate_ticket_code() -> str:
    db = get_client()
    res = db.table("support_tickets").select("id", count="exact").execute()
    n = (res.count or 0) + 1
    return f"TCK-{n:06d}"


def create_support_ticket(user_id: int, message: str, image_file_ids: list[tuple[str, str]]) -> dict:
    db = get_client()
    code = _generate_ticket_code()
    result = db.table("support_tickets").insert({
        "ticket_code": code, "user_id": user_id, "message": message,
    }).execute()
    ticket = result.data[0]
    for file_id, file_type in image_file_ids:
        db.table("support_ticket_images").insert({
            "ticket_id": ticket["id"], "file_id": file_id, "file_type": file_type,
        }).execute()
    return ticket


def get_ticket_by_code(code: str) -> dict | None:
    db = get_client()
    res = db.table("support_tickets").select("*").eq("ticket_code", code).execute()
    return res.data[0] if res.data else None


def set_ticket_admin_channel_message_id(code: str, message_id: int) -> None:
    get_client().table("support_tickets").update(
        {"admin_channel_message_id": message_id}
    ).eq("ticket_code", code).execute()


def reply_to_ticket(code: str, reply: str) -> dict:
    db = get_client()
    db.table("support_tickets").update({
        "admin_reply": reply, "status": "answered",
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }).eq("ticket_code", code).execute()
    return get_ticket_by_code(code)
