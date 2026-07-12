"""
State name constants for the conversation finite-state-machine. Stored as
plain strings in the `sessions.state` column in Supabase (see db/queries.py).
Keeping them as constants here avoids typos scattered across handler files.
"""

IDLE = "idle"

# --- New application form ---
APP_COURIER = "app_courier"
APP_TRACKING = "app_tracking"
APP_AMOUNT = "app_amount"
APP_NOTES = "app_notes"
APP_PRIORITY = "app_priority"
APP_IMAGES = "app_images"

# --- Awaiting user's reply to an admin "Need More Info" request ---
AWAITING_USER_INFO_REPLY = "awaiting_user_info_reply"

# --- Payment collection (triggered after admin approval) ---
AWAITING_PAYMENT_METHOD = "awaiting_payment_method"
AWAITING_CRYPTO_COIN = "awaiting_crypto_coin"
AWAITING_CRYPTO_WALLET = "awaiting_crypto_wallet"
AWAITING_PAYMENT_HANDLE = "awaiting_payment_handle"

# --- Support ---
AWAITING_SUPPORT_MESSAGE = "awaiting_support_message"
AWAITING_SUPPORT_IMAGES = "awaiting_support_images"

# Ordered sequence of the core application form — used to know "what's next"
APPLICATION_FORM_SEQUENCE = [APP_COURIER, APP_TRACKING, APP_AMOUNT, APP_NOTES, APP_PRIORITY, APP_IMAGES]
