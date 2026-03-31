"""Handlers for /start, /help, and /status commands."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import TELEGRAM_USER_ID
from bot.services.supabase_client import get_daily_record

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """Welcome to your Daily Tracker Bot!

I'll message you every evening to collect your daily health data, pull your Whoop metrics, and update your Google Sheet automatically.

*Commands:*
/checkin — Start the evening check-in
/status — See what's been logged today
/setup\\_whoop — One-time Whoop authorization
/help — Show this message

You can also send me a voice note anytime to update your data, or text like "weight was 68.5" to fix a field."""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        return
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        return

    today = date.today()
    record = get_daily_record(today.isoformat())

    if not record:
        await update.message.reply_text(
            f"No data logged yet for {today.strftime('%B %d')}. "
            "Use /checkin to start, or send a voice note."
        )
        return

    lines = [f"*{today.strftime('%B %d')} — Today's Data:*\n"]

    field_labels = {
        "weight_kg": "Weight",
        "resting_hr": "Resting HR",
        "hrv_rmssd": "HRV",
        "water_liters": "Water (L)",
        "body_fat_pct": "Body Fat %",
        "session_performed": "Session",
        "strength_rating": "Strength",
        "cardio_duration_min": "Cardio (min)",
        "daily_steps": "Steps",
        "morning_readiness": "Readiness",
        "energy": "Energy",
        "hunger": "Hunger",
        "stress": "Stress",
        "illness": "Illness",
        "digestion_issue": "Digestion",
        "bed_time": "Bed Time",
        "sleep_duration_minutes": "Sleep Duration",
        "deep_rem_minutes": "Deep+REM",
        "stuck_to_plan": "Stuck to Plan",
    }

    for key, label in field_labels.items():
        val = record.get(key)
        if val is not None:
            if key == "illness":
                val = "Yes" if val else "No"
            elif key == "stuck_to_plan":
                val = "Yes" if val else "No"
            elif key in ("sleep_duration_minutes", "deep_rem_minutes") and isinstance(val, int):
                h, m = divmod(val, 60)
                val = f"{h}h {m}m"
            lines.append(f"  {label}: {val}")

    whoop = "Yes" if record.get("whoop_synced") else "No"
    sheet = "Yes" if record.get("sheet_synced") else "No"
    lines.append(f"\n_Whoop synced: {whoop} | Sheet synced: {sheet}_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
