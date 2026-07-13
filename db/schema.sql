-- ============================================================================
-- Cash In The Hat Bot — Database Schema (Supabase / PostgreSQL)
-- ============================================================================
-- Run this entire file once in the Supabase SQL Editor (Project > SQL Editor
-- > New query) after creating your project. It is safe to re-run: every
-- statement uses IF NOT EXISTS / CREATE OR REPLACE where possible.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- ENUM TYPES
-- ----------------------------------------------------------------------------

do $$ begin
    create type application_status as enum (
        'pending',              -- just submitted, not yet reviewed
        'under_review',         -- admin actively looking at it
        'awaiting_user_response', -- admin asked for more info, waiting on user
        'approved',             -- admin approved, waiting on payout info
        'rejected',             -- admin rejected
        'in_progress',          -- refund is being processed
        'completed'             -- finished / paid out
    );
exception
    when duplicate_object then null;
end $$;

do $$ begin
    create type ticket_status as enum ('open', 'answered', 'closed');
exception
    when duplicate_object then null;
end $$;

-- ----------------------------------------------------------------------------
-- USERS
-- ----------------------------------------------------------------------------
create table if not exists users (
    telegram_id     bigint primary key,
    username        text,
    first_name      text,
    is_verified     boolean not null default false,   -- passed channel membership check
    created_at      timestamptz not null default now(),
    last_active_at  timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- SESSIONS  (Finite State Machine storage — required because Vercel functions
-- are stateless between invocations; all "where is this user in the
-- conversation" data lives here instead of in memory.)
-- ----------------------------------------------------------------------------
create table if not exists sessions (
    telegram_id     bigint primary key,
    state           text not null default 'idle',
    context         jsonb not null default '{}'::jsonb,
    updated_at      timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- APPLICATIONS
-- ----------------------------------------------------------------------------
create sequence if not exists application_code_seq start 1;

create table if not exists applications (
    id                  bigserial primary key,
    application_code    text unique not null,          -- e.g. CIH-000123
    user_id             bigint not null references users(telegram_id),
    status              application_status not null default 'pending',

    store_name          text,
    order_number        text,
    account_email       text,
    verification_code   text,
    order_total          text,
    tracking_numbers    text,
    order_status        text,                          -- client-reported status (Delivered, In Transit, etc.)
    desired_resolution  text,                          -- Refund | Replacement | Store Credit
    notes               text,
    is_priority         boolean not null default false,
    priority_fee        numeric(10,2),                  -- e.g. 20.00 when is_priority is true

    payment_method      text,                          -- 'cashapp' | 'paypal' | 'zelle' | 'crypto' — pays OUR service fee
    payment_details      jsonb,                          -- {"handle": "..."} or {"coin": "...", "wallet": "..."}

    admin_channel_message_id bigint,                    -- to edit the admin-channel post as status changes

    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create index if not exists idx_applications_user on applications(user_id);
create index if not exists idx_applications_status on applications(status);

-- ----------------------------------------------------------------------------
-- APPLICATION IMAGES  (we store Telegram file_ids only — no external storage)
-- ----------------------------------------------------------------------------
create table if not exists application_images (
    id              bigserial primary key,
    application_id  bigint not null references applications(id) on delete cascade,
    file_id         text not null,
    file_type       text not null default 'photo',      -- 'photo' | 'document'
    uploaded_at     timestamptz not null default now()
);

create index if not exists idx_app_images_app on application_images(application_id);

-- ----------------------------------------------------------------------------
-- APPLICATION STATUS HISTORY  (audit trail + powers "Last Updated" display)
-- ----------------------------------------------------------------------------
create table if not exists application_status_history (
    id              bigserial primary key,
    application_id  bigint not null references applications(id) on delete cascade,
    old_status      application_status,
    new_status      application_status not null,
    changed_by      bigint,                             -- admin telegram_id, null if system
    note            text,
    created_at      timestamptz not null default now()
);

create index if not exists idx_status_history_app on application_status_history(application_id);

-- ----------------------------------------------------------------------------
-- SUPPORT TICKETS
-- ----------------------------------------------------------------------------
create table if not exists support_tickets (
    id              bigserial primary key,
    ticket_code     text unique not null,               -- e.g. TCK-000045
    user_id         bigint not null references users(telegram_id),
    message         text not null,
    status          ticket_status not null default 'open',
    admin_reply     text,
    admin_channel_message_id bigint,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create table if not exists support_ticket_images (
    id              bigserial primary key,
    ticket_id       bigint not null references support_tickets(id) on delete cascade,
    file_id         text not null,
    file_type       text not null default 'photo'
);

-- ----------------------------------------------------------------------------
-- RATE LIMITING  (generic event log; queried with a time-window count)
-- ----------------------------------------------------------------------------
create table if not exists rate_events (
    id              bigserial primary key,
    telegram_id     bigint not null,
    action          text not null,                      -- 'new_application' | 'button' | 'form_message'
    created_at      timestamptz not null default now()
);

create index if not exists idx_rate_events_lookup on rate_events(telegram_id, action, created_at);

-- Housekeeping: old rate-limit rows are cheap to keep, but you can periodically
-- prune them with:
--   delete from rate_events where created_at < now() - interval '1 day';

-- ----------------------------------------------------------------------------
-- ADMIN PENDING ACTIONS  (tracks "admin clicked Need More Info, we're waiting
-- for their free-text reply in DM")
-- ----------------------------------------------------------------------------
-- Keyed by the admin's own Telegram ID. When an admin clicks "Need More
-- Info" or "Reply" on a ticket, the bot DMs that admin privately to collect
-- their free-text response (channels don't let the bot attribute a channel
-- post to a specific admin, so this happens in DM instead of in-channel).
create table if not exists admin_pending_actions (
    admin_telegram_id   bigint primary key,
    action              text not null,                  -- 'awaiting_more_info_text' | 'awaiting_ticket_reply_text'
    reference_id        bigint not null,                -- application.id or support_tickets.id depending on action
    created_at          timestamptz not null default now()
);

-- ----------------------------------------------------------------------------
-- HELPER FUNCTION — atomic application code counter
-- (Called via Supabase's .rpc() from Python so numbering never collides
-- even if two applications are submitted at the exact same millisecond.)
-- ----------------------------------------------------------------------------
create or replace function nextval_application_code()
returns bigint
language sql
as $$
    select nextval('application_code_seq');
$$;

-- ============================================================================
-- End of schema
-- ============================================================================
