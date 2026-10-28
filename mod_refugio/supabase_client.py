import os

from supabase import create_client

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")

supabase = (
    create_client(supabase_url, supabase_key)
    if supabase_url and supabase_key
    else None
)
