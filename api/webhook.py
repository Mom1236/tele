"""
Vercel serverless entry point. Deployed as api/webhook.py, so Telegram's
webhook URL will be: https://<your-project>.vercel.app/api/webhook

Vercel's @vercel/python builder auto-detects the `app` Flask/WSGI object
and serves it for every request to this route.
"""
import logging
import sys
import os

# Ensure the project root is importable (Vercel packages the whole repo).
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from bot.config import WEBHOOK_SECRET
from bot.router import route_update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook")

app = Flask(__name__)


@app.route("/api/webhook", methods=["POST"])
def webhook():
    # Verify the request truly came from Telegram using the secret token
    # configured when the webhook was registered (setWebhook secret_token param).
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_header != WEBHOOK_SECRET:
        logger.warning("Rejected webhook call with invalid secret token.")
        return jsonify({"ok": False}), 401

    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": False, "error": "no json body"}), 400

    route_update(update)

    # Always return 200 quickly — Telegram retries aggressively on non-2xx.
    return jsonify({"ok": True})


@app.route("/api/webhook", methods=["GET"])
def health_check():
    return jsonify({"ok": True, "status": "Cash In The Hat bot is running."})
