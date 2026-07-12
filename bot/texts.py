"""
All user-facing copy lives here so tone stays consistent and easy to edit.
Voice: premium, professional, exclusive, concierge-style. No emoji clutter,
no "Hey there!" energy — this should read like a private members' service.
"""

# --- Verification -----------------------------------------------------------
NOT_A_MEMBER = (
    "Access to Cash In The Hat is reserved for members of our private channel.\n\n"
    "Please join to continue, then confirm your membership below."
)
VERIFICATION_SUCCESS = (
    "Membership confirmed. Welcome to Cash In The Hat — your private refund "
    "concierge service."
)
VERIFICATION_FAILED = (
    "We were unable to confirm your membership. Please join the channel first, "
    "then try again."
)

# --- Main menu ---------------------------------------------------------------
WELCOME_BACK = "Welcome back. How may we assist you today?"

# --- Application form ---------------------------------------------------------
ASK_COURIER = "Which shipping courier was used for this order?"
ASK_TRACKING = "Please provide the tracking number(s) associated with this order."
ASK_AMOUNT = "What is the order amount? (e.g. $1,250.00)"
ASK_NOTES = (
    "Is there anything else our team should know about this request? "
    "You may also reply \"None\" if not applicable."
)
ASK_PRIORITY = "Would you like to request priority processing for this application?"
ASK_IMAGES = (
    "You may now attach supporting materials — order screenshots, email "
    "confirmations, or other documentation (up to 10 images or PDFs).\n\n"
    "Send them one at a time, or press Skip to continue without attachments."
)
IMAGE_RECEIVED = "Attachment received ({count}/{max}). Send another, or press Done to continue."
IMAGE_LIMIT_REACHED = "You've reached the maximum of {max} attachments. Continuing to submission."

APPLICATION_SUBMITTED = (
    "Your request has been successfully submitted and is now under review by our team.\n\n"
    "Application ID: {code}\n\n"
    "You may check its status at any time from the main menu."
)

DRAFT_RESUME_PROMPT = "You have an unfinished application in progress."
MAX_ACTIVE_APPLICATIONS_REACHED = (
    "You currently have the maximum number of active applications ({max}) open at once. "
    "Please wait for one to be resolved before submitting a new request."
)

# --- Status / history ----------------------------------------------------------
NO_APPLICATIONS_YET = "You have not yet submitted a request with us."
STATUS_LABELS = {
    "pending": "Pending Review",
    "under_review": "Under Review",
    "awaiting_user_response": "Awaiting Your Response",
    "approved": "Approved",
    "rejected": "Not Approved",
    "in_progress": "In Progress",
    "completed": "Completed",
}

def application_detail(code: str, status_label: str, courier: str, tracking: str,
                        amount: str, priority: bool, updated_at: str) -> str:
    priority_line = "\n🔥 Priority Request" if priority else ""
    return (
        f"Application {code}{priority_line}\n\n"
        f"Status: {status_label}\n"
        f"Courier: {courier or '—'}\n"
        f"Tracking: {tracking or '—'}\n"
        f"Amount: {amount or '—'}\n\n"
        f"Last Updated: {updated_at}"
    )

# --- Admin-driven status updates delivered to the user ------------------------
USER_NOTICE_APPROVED = (
    "Your request has been approved. Please provide your preferred payment "
    "method to continue."
)
USER_NOTICE_REJECTED = (
    "After careful review, we are unable to approve this request at this time. "
    "If you believe this was in error, please reach out through Support."
)
USER_NOTICE_IN_PROGRESS = "Your request is now being processed by our team."
USER_NOTICE_COMPLETED = (
    "Your request has been completed. Thank you for trusting Cash In The Hat "
    "with your business."
)
USER_NOTICE_MORE_INFO = (
    "Our team requires additional information regarding your request {code}:\n\n"
    "\"{message}\"\n\n"
    "Please reply directly below."
)
USER_INFO_REPLY_RECEIVED = (
    "Thank you — your response has been forwarded to our team and your "
    "request is once again under review."
)

# --- Payment collection ---------------------------------------------------------
ASK_PAYMENT_METHOD = "How would you like to receive payment?"
ASK_CRYPTO_COIN = "Which coin would you like to be paid in? (e.g. BTC, ETH, USDT)"
ASK_CRYPTO_WALLET = "Please provide your wallet address for this coin."
ASK_PAYMENT_HANDLE = "Please provide the username, email, or phone number associated with this payment method."
PAYMENT_INFO_RECEIVED = (
    "Thank you. Your payout details have been recorded and shared with our team. "
    "We will be in touch shortly to complete your request."
)

# --- Support -------------------------------------------------------------------
SUPPORT_PROMPT = "How can we help you today? You may also attach screenshots if helpful."
SUPPORT_TICKET_CREATED = (
    "Your message has been received. A member of our team will respond to you "
    "directly here as soon as possible.\n\nReference: {code}"
)
SUPPORT_REPLY_TO_USER = "A response has been sent regarding your support request {code}:\n\n{message}"

# --- Rate limiting / errors ------------------------------------------------------
RATE_LIMITED = "Please wait a few moments before trying again."
GENERIC_ERROR = "Something went wrong on our end. Please try again shortly, or contact Support."

# --- Admin channel formatting --------------------------------------------------
def admin_application_card(code: str, username: str, telegram_id: int, status_label: str,
                            courier: str, tracking: str, amount: str, priority: bool,
                            notes: str, has_attachments: bool) -> str:
    priority_badge = "\n🔥 Priority Request" if priority else ""
    handle = f"@{username}" if username else "(no username)"
    return (
        f"New Application{priority_badge}\n\n"
        f"ID: {code}\n"
        f"User: {handle}\n"
        f"Telegram ID: {telegram_id}\n\n"
        f"Courier: {courier or '—'}\n"
        f"Tracking: {tracking or '—'}\n"
        f"Amount: {amount or '—'}\n\n"
        f"Notes:\n{notes or '—'}\n\n"
        f"Attachments: {'Yes' if has_attachments else 'None'}\n"
        f"Status: {status_label}"
    )

def admin_payment_update(code: str, method: str, details: dict) -> str:
    if method == "crypto":
        detail_line = f"Coin: {details.get('coin')}\nWallet: {details.get('wallet')}"
    else:
        detail_line = f"Handle: {details.get('handle')}"
    return f"Payment details received for {code}\n\nMethod: {method.title()}\n{detail_line}"

def admin_support_card(code: str, username: str, telegram_id: int, message: str,
                        has_attachments: bool) -> str:
    handle = f"@{username}" if username else "(no username)"
    return (
        f"New Support Ticket\n\n"
        f"Ref: {code}\n"
        f"User: {handle}\n"
        f"Telegram ID: {telegram_id}\n\n"
        f"Message:\n{message}\n\n"
        f"Attachments: {'Yes' if has_attachments else 'None'}"
    )

ASK_ADMIN_MORE_INFO_TEXT = "What information would you like to request from this user for {code}?"
