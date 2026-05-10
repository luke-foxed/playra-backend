import os

from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

_client = None

def get_supabase_client() -> Client:
    global _client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase environment variables")

    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)

    return _client