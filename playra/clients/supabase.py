import os

from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

client: Client | None = None

def get_supabase_client() -> Client:
    global client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Missing Supabase environment variables")

    if client is None:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)

    return client