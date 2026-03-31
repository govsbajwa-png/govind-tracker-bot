"""Handle ad-hoc text messages outside check-in flow for updating specific fields."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import TELEGRAM_USER_ID, SHEET_COLUMNS
from bot.services.extraction import extract_health_data
from bot.services.sheets import SheetsService
from bot.services.supabase_client import get_daily_record, upsert_daily_record
from bot.handlers.setup import handle_whoop_callback

logger = logging.getLogger(__name__)

# Map extraction keys to DailyRecord field names and sheet columns
FIELD_MAP = {
    "weight": ("weight_kg", "C"),
    "water": ("water_liters", "F"),
    "body_fat": ("body_fat_pct", "G"),
    "readiness": ("morning_readiness", "L"),
    "energy": ("energy", "M"),
    "stress": ("stress", "O"),
    "hunger": ("hunger", "N"),
    "strength": ("strength_rating", "I"),
    "illness": ("illness", "P"),
    "digestion": ("digestion_issue", "Q"),
    "plan": ("stuck_to_plan", "U"),
    "session": ("session_performed", "H"),
}


async def adhoc_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-text messages for ad-hoc field updates."""
    if update.effective_user.id != TELEGRAM_USER_ID:
        return

    # Skip if in check-in flow
    if context.user_data.get("in_checkin"):
        return

    # Check if this is a Whoop OAuth callback URL
    handled = await handle_whoop_callback(update, context)
    if handled:
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    # Skip commands
    if text.startswith("/"):
        return

    # Try to extract health data from the message
    extracted = await extract_health_data(text)
    if not extracted:
        # Don't respond to random messages — only health data updates
        return

    today = date.today()

    # Get existing record
    existing = get_daily_record(today.isoformat()) or {}

    # Build update dict
    updates = {}
    sheet_updates = {}

    for extract_key, value in extracted.items():
        if value is None:
            continue
        mapping = FIELD_MAP.get(extract_key)
        if mapping:
            db_field, col_letter = mapping
            updates[db_field] = value
            # Format for sheet
            if isinstance(value, bool):
                sheet_updates[col_letter] = "Yes" if value else "No"
            else:
                sheet_updates[col_letter] = value

    if not updates:
        return

    # Update Supabase
    record_data = {**existing, **updates, "date": today.isoformat()}
    # Remove non-column keys
    for key in ("id", "created_at", "updated_at"):
        record_data.pop(key, None)
    upsert_daily_record(record_data)

    # Update Sheet
    try:
        sheets = SheetsService()
        date_str = sheets.find_row_for_date(today)
        for col_letter, value in sheet_updates.items():
            sheets.update_single_field(date_str, col_letter, value)
    except Exception as e:
        logger.error("Sheet update failed: %s", e)

    # Confirm
    summary = ", ".join(f"{k}: {v}" for k, v in updates.items())
    await update.message.reply_text(f"Updated for today: {summary}")
