"""
Single shared Supabase client. Vercel reuses warm containers between
invocations sometimes, so we cache the client at module level — cheap when
reused, harmless to recreate on a cold start.
"""
from supabase import create_client, Client
from bot.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client
