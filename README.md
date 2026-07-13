# Cash In The Hat — Telegram Concierge Bot

A private, invite-gated Telegram bot for collecting refund-service applications,
routing them through an admin review pipeline, and collecting payout details —
built for Python + Vercel serverless webhooks + Supabase (Postgres).

---

## 1. Architecture Overview

```
Telegram  ──POST──▶  /api/webhook (Vercel serverless, Flask)
                          │
                          ▼
                    bot/router.py  (decides: DM? admin channel? which flow?)
                          │
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                      ▼
  bot/handlers/*     bot/middleware.py      bot/telegram_api.py
  (business logic)   (verify + rate limit)  (thin Bot API wrapper)
        │
        ▼
   db/queries.py  ──▶  Supabase (Postgres)
```

**Why this shape:**
- Vercel Python functions are **stateless** — nothing survives between
  requests in memory. So the entire conversation state machine (what step of
  the form a user is on, draft answers, pending admin replies) lives in
  Supabase's `sessions` table, not in a Python variable.
- We use raw `requests` calls to the Telegram Bot API instead of a heavy
  library like `python-telegram-bot`, because that library's async runtime
  fights with Vercel's short-lived WSGI invocation model and adds cold-start
  weight for no benefit here.
- The **admin chat is a regular Telegram broadcast channel.** Buttons
  (Approve/Reject/Need More Info/Mark Complete, and Reply on tickets) work
  fine in a channel — Telegram's callback_query always carries the identity
  of whoever clicked, even in a channel. What doesn't work in a channel is
  attributing a *typed message* to a specific admin. So whenever an admin
  needs to type something (answering "what info do you need?", or replying
  to a support ticket), the bot DMs that specific admin privately to collect
  it, then forwards it on — the channel itself stays read-only/broadcast.
- **Admin typed commands** (`/stats`, `/broadcast`, `/application`,
  `/setstatus`) are run by **DMing the bot directly**, which keeps every
  admin text interaction — commands and reply flows alike — in one
  consistent place: a private conversation with the bot.

---

## 2. Database Schema

See [`db/schema.sql`](db/schema.sql) — run this once in the Supabase SQL
Editor. Summary of tables:

| Table | Purpose |
|---|---|
| `users` | Telegram users + verification status |
| `sessions` | FSM state + in-progress draft data per user |
| `applications` | The core refund applications, one row per submission |
| `application_images` | Telegram `file_id`s attached to an application |
| `application_status_history` | Full audit trail of every status change |
| `support_tickets` / `support_ticket_images` | Support flow |
| `rate_events` | Generic event log used to enforce all rate limits |
| `admin_pending_actions` | Tracks "Need More Info" prompts awaiting an admin's reply |

Application IDs are generated atomically via a Postgres sequence
(`application_code_seq`) exposed through the `nextval_application_code()`
SQL function, so concurrent submissions never collide — formatted as
`CIH-000123`.

---

## 3. Folder Structure

```
cash-in-the-hat-bot/
├── api/
│   └── webhook.py            # Vercel serverless entry point (Flask app)
├── bot/
│   ├── config.py              # env var loading
│   ├── texts.py                # ALL user-facing copy (premium tone)
│   ├── keyboards.py            # inline keyboard builders
│   ├── telegram_api.py         # Bot API wrapper (requests-based)
│   ├── fsm.py                  # conversation state constants
│   ├── utils.py                 # small helpers
│   ├── middleware.py            # verification + rate-limit gates
│   ├── router.py                 # top-level update dispatcher
│   └── handlers/
│       ├── start.py              # /start, membership verification
│       ├── application.py        # new application multi-step form
│       ├── payment.py            # payout info collection (post-approval)
│       ├── support.py            # support ticket flow
│       ├── admin.py              # admin buttons + text commands
│       └── callback_router.py    # dispatches all inline button presses
├── db/
│   ├── client.py                # Supabase client singleton
│   ├── queries.py                # all DB reads/writes
│   └── schema.sql                 # full Postgres schema
├── requirements.txt
├── vercel.json
├── .env.example
├── test_local.py                # local smoke test harness
└── README.md
```

---

## 4. API Design

Single route: **`POST /api/webhook`** — this is the only endpoint. Telegram
sends every update (messages, button presses) here. A `GET` on the same path
returns a simple health-check JSON so you can confirm the deployment is live.

Security: every incoming POST is checked against the
`X-Telegram-Bot-Api-Secret-Token` header, which must match `WEBHOOK_SECRET`.
This is set when you register the webhook (step 6 below) and prevents anyone
who guesses your URL from injecting fake Telegram updates.

---

## 5. Conversation Flows

### New user
```
/start → membership check (live) →
  not a member → "Join Channel" / "I've Joined" buttons
  is a member  → main menu (or "resume draft" if one exists)
```

### New application
```
Submit New Application
  → check: < 3 active applications? not in 10-min cooldown?
  → Courier → Tracking → Amount → Notes → Priority (Y/N) → Images (0–10, Done/Skip)
  → generate CIH-###### → save to DB → confirm to user → post to admin channel
```

### Admin review (buttons on the admin-channel card)
```
Approve        → status=approved   → DM user → start payment collection flow
Reject         → status=rejected   → DM user
Mark Complete  → status=completed  → DM user
Need More Info → bot DMs the clicking admin privately: "what info do you need?"
               → admin types the reply in that DM → status=awaiting_user_response
               → user DM'd the request → user replies → status=under_review
```

### Payment collection (triggered right after Approve)
```
"How would you like to receive payment?" [Cash App] [PayPal] [Zelle] [Crypto]
  Crypto → ask coin → ask wallet → save → notify admin channel
  Other  → ask handle (username/email/phone) → save → notify admin channel
```

### Support
```
Support → "How can we help?" → message (+ optional screenshots, "done" to finish)
  → ticket posted to admin channel with a Reply button
  → admin clicks Reply → bot DMs that admin privately for the reply text
  → user DM'd the response
```

---

## 6. Deployment Plan

1. Create Supabase project → run `db/schema.sql`.
2. Create the bot with @BotFather → get `BOT_TOKEN`.
3. Create your private client channel + admin channel in Telegram; add the
   bot to both as an admin.
4. Push this repo to GitHub, import into Vercel, set environment variables
   (see below), deploy.
5. Register the webhook (one-time call — see step 6 in Installation).
6. Test with `/start` from a real Telegram account.

---

## 7. Environment Variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | From @BotFather |
| `WEBHOOK_SECRET` | Any long random string you choose — validates incoming requests |
| `PRIVATE_CHANNEL_ID` | Numeric ID of your gated channel, e.g. `-1001234567890` |
| `PRIVATE_CHANNEL_INVITE_LINK` | Public invite link shown on the "Join Channel" button |
| `ADMIN_CHANNEL_ID` | Numeric ID of your admin channel (applications/tickets are posted here) |
| `ADMIN_IDS` | Comma-separated Telegram user IDs allowed to use admin features |
| `SUPABASE_URL` | From Supabase project settings |
| `SUPABASE_SERVICE_KEY` | Supabase **service_role** key (server-side only, never expose client-side) |

---

## 8. Vercel Configuration

`vercel.json` is already set up to build `api/webhook.py` as a Python
serverless function and route `/api/webhook` to it. No further config needed
beyond setting the environment variables in the Vercel dashboard
(Project → Settings → Environment Variables).

---

## 9. Installation Instructions

### Step 1 — Create the Supabase project
1. Go to [supabase.com](https://supabase.com) → New Project.
2. Once created, go to **SQL Editor → New Query**, paste the entire contents
   of `db/schema.sql`, and run it.
3. Go to **Project Settings → API** and copy the **Project URL** and the
   **service_role** secret key (not the anon key — the bot needs full write
   access and runs server-side only).

### Step 2 — Create the bot
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts.
2. Save the token it gives you.
3. Optionally set a description/photo with `/setdescription`, `/setuserpic`.

### Step 3 — Set up Telegram chats
1. Create your **private channel** (or use an existing one) — this is where
   paying clients live. Get its numeric ID (see tip below).
2. Create your **admin channel** — this is where every application and
   support ticket gets posted for review. It can be a normal broadcast
   channel; it does not need to be a group.
3. Add the bot to **both** channels as an **admin**, with permission to post
   messages (needed to send cards) — for the private client channel it also
   needs enough access for `getChatMember` membership checks to work.
4. **Important:** each admin listed in `ADMIN_IDS` must message the bot
   directly at least once (e.g. send `/start` to it in DM) before the bot
   can DM them. Telegram doesn't allow bots to cold-message a user who has
   never opened a chat with it — this is what makes the "Need More Info"
   and ticket-reply DM prompts possible.

**Tip — getting a numeric chat ID:** Add [@userinfobot](https://t.me/userinfobot)
or [@RawDataBot](https://t.me/RawDataBot) to the channel temporarily, or
forward a message from that channel to @userinfobot in DM.

### Step 4 — Clone and configure locally
```bash
git clone <your-repo-url>
cd cash-in-the-hat-bot
cp .env.example .env
# fill in every value in .env
pip install -r requirements.txt
```

### Step 5 — Deploy to Vercel
```bash
npm install -g vercel   # if you don't have it
vercel login
vercel                  # first deploy, follow prompts
```
Then in the Vercel dashboard, add every variable from `.env.example` under
**Settings → Environment Variables** (for Production, and Preview if you
plan to test there too), and redeploy:
```bash
vercel --prod
```

### Step 6 — Register the webhook with Telegram
Run this once (replace placeholders):
```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://<your-vercel-domain>/api/webhook" \
  -d "secret_token=<WEBHOOK_SECRET>"
```
Confirm it worked:
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

---

## 10. Local Testing Instructions

You can exercise the full logic locally against your real Supabase project
without deploying, using Flask's test client:

```bash
cp .env.example .env      # fill in real values
python test_local.py
```

This simulates a `/start` update being POSTed to the webhook exactly as
Telegram would send it, and prints the Flask response. Since it calls the
real Telegram API to send messages, use a real (test) bot token and check
your own Telegram DM with the bot to see the result.

To test other flows (button presses, form steps), copy `fake_start_update`
in `test_local.py` and modify it — e.g. for a callback query:
```python
fake_callback = {
    "update_id": 2,
    "callback_query": {
        "id": "abc123",
        "from": {"id": TEST_CHAT_ID, "username": "testuser"},
        "message": {"message_id": 1, "chat": {"id": TEST_CHAT_ID}},
        "data": "menu_new_application",
    },
}
```

For fully offline testing (no real Telegram calls), monkeypatch
`bot.telegram_api._call` to just log/print instead of hitting the network.

---

## 11. Production Deployment Checklist

- [ ] `db/schema.sql` applied to Supabase
- [ ] Bot added as admin to both the private channel and the admin channel
- [ ] Every admin in `ADMIN_IDS` has DM'd the bot at least once (so it can message them)
- [ ] All environment variables set in Vercel (Production environment)
- [ ] Webhook registered with the correct `secret_token`
- [ ] `getWebhookInfo` shows no `last_error_message`
- [ ] Sent a real `/start` from a non-admin test account and confirmed the
      full flow: verification → new application → images → submission →
      admin channel card appears → Approve → payment info collection → DM
      confirmations at each step
- [ ] Tested `/stats`, `/application <code>`, `/setstatus`, `/broadcast`
      from an admin account via DM
- [ ] Confirmed rate limits trigger the "please wait" message when exceeded
- [ ] Rotate `WEBHOOK_SECRET` and Supabase service key if either was ever
      shared/pasted anywhere public

---

## 12. Notes, Limitations & Next Steps

- **No payment processing** — by design, this only *collects* payout
  details (Cash App/PayPal/Zelle handle, or crypto coin + wallet). You pay
  clients manually outside the bot.
- **Images** are stored as Telegram `file_id`s only — no external storage
  bucket, so they're only retrievable through the bot/Telegram, which is
  fine for admin review but means they're not independently downloadable
  outside Telegram.
- The `ADMIN_IDS` env var already supports multiple comma-separated IDs —
  adding a second admin today just means adding their ID to that string.
- The schema and handler structure were built with the roadmap in mind:
  multiple admin channels, a referral system, analytics, broadcast
  campaigns, application categories, and user history/reputation can all be
  added as new tables/columns without restructuring what exists.
- This is a solid production-ready **scaffold** — before handling real
  client money, do a full run-through with a test channel and a
  throwaway Supabase project first.
