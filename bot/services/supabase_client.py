"""Supabase client service for persistent storage."""

from supabase import create_client, Client

from bot.config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_daily_record(record_dict: dict) -> dict:
    """Upsert a daily record using `date` as the conflict key."""
    result = (
        supabase.table("daily_records")
        .upsert(record_dict, on_conflict="date")
        .execute()
    )
    return result.data[0] if result.data else {}


def get_daily_record(date_str: str) -> dict | None:
    """Get a single daily record by date string (YYYY-MM-DD)."""
    result = (
        supabase.table("daily_records")
        .select("*")
        .eq("date", date_str)
        .maybe_single()
        .execute()
    )
    return result.data


def save_whoop_tokens(
    access_token: str, refresh_token: str, expires_at: int
) -> None:
    """Upsert Whoop OAuth tokens (singleton row, id=1)."""
    supabase.table("whoop_tokens").upsert(
        {
            "id": 1,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
        }
    ).execute()


def get_whoop_tokens() -> dict | None:
    """Retrieve stored Whoop OAuth tokens."""
    result = (
        supabase.table("whoop_tokens")
        .select("*")
        .eq("id", 1)
        .maybe_single()
        .execute()
    )
    return result.data


def save_memory(key: str, value: dict) -> None:
    """Upsert a key-value pair into conversation_memory."""
    supabase.table("conversation_memory").upsert(
        {"key": key, "value": value}, on_conflict="key"
    ).execute()


def get_memory(key: str) -> dict | None:
    """Get a value from conversation_memory by key."""
    result = (
        supabase.table("conversation_memory")
        .select("*")
        .eq("key", key)
        .maybe_single()
        .execute()
    )
    return result.data
