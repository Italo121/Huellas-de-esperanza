import os

from supabase import create_client

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase_secret_key = os.environ.get("SUPABASE_SECRET_KEY")

supabase = (
    create_client(supabase_url, supabase_key)
    if supabase_url and supabase_key
    else None
)

supabase_storage = (
    create_client(supabase_url, supabase_secret_key)
    if supabase_url and supabase_secret_key
    else None
)
