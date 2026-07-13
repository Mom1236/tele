"""
State name constants for the conversation finite-state-machine. Stored as
plain strings in the `sessions.state` column in Supabase (see db/queries.py).
Keeping them as constants here avoids typos scattered across handler files.
"""

IDLE = "idle"

# --- New application form ---
APP_STORE_NAME = "app_store_name"
APP_ORDER_NUMBER = "app_order_number"
APP_ACCOUNT_EMAIL = "app_account_email"
APP_VERIFICATION_CODE = "app_verification_code"
APP_ORDER_TOTAL = "app_order_total"
APP_TRACKING = "app_tracking"
APP_ORDER_STATUS = "app_order_status"
APP_DESIRED_RESOLUTION = "app_desired_resolution"
APP_NOTES = "app_notes"
APP_PRIORITY = "app_priority"
APP_PAYMENT_METHOD = "app_payment_method"
APP_CRYPTO_COIN = "app_crypto_coin"
APP_CRYPTO_WALLET = "app_crypto_wallet"
APP_PAYMENT_HANDLE = "app_payment_handle"
APP_IMAGES = "app_images"

# --- Awaiting user's reply to an admin "Need More Info" request ---
AWAITING_USER_INFO_REPLY = "awaiting_user_info_reply"

# --- Support ---
AWAITING_SUPPORT_MESSAGE = "awaiting_support_message"
AWAITING_SUPPORT_IMAGES = "awaiting_support_images"

# Ordered sequence of the core application form — used to know "what's next"
# and to let the router recognize "the user is somewhere in this form."
APPLICATION_FORM_SEQUENCE = [
    APP_STORE_NAME, APP_ORDER_NUMBER, APP_ACCOUNT_EMAIL, APP_VERIFICATION_CODE,
    APP_ORDER_TOTAL, APP_TRACKING, APP_ORDER_STATUS, APP_DESIRED_RESOLUTION,
    APP_NOTES, APP_PRIORITY, APP_PAYMENT_METHOD, APP_CRYPTO_COIN,
    APP_CRYPTO_WALLET, APP_PAYMENT_HANDLE, APP_IMAGES,
]

PRIORITY_FEE_AMOUNT = 20.00
