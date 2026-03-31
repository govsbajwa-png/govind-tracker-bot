"""Handle voice notes: download, transcribe, extract structured data."""

import logging
from io import BytesIO

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import TELEGRAM_USER_ID
from bot.services.transcription import transcribe_voice_async as transcribe_voice
from bot.services.extraction import extract_health_data

logger = logging.getLogger(__name__)


async def process_voice_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Download voice note, transcribe, extract data. Returns extracted dict.

    This is called both from the check-in flow (as interrupt) and standalone.
    """
    voice = update.message.voice or update.message.audio
    if not voice:
        return {}

    # Download the audio file
    file = await context.bot.get_file(voice.file_id)
    buf = BytesIO()
    await file.download_to_memory(buf)
    audio_bytes = buf.getvalue()

    logger.info("Downloaded voice note: %d bytes", len(audio_bytes))

    # Transcribe
    transcript = await transcribe_voice(audio_bytes)
    if not transcript:
        logger.warning("Empty transcript from voice note")
        return {}

    logger.info("Transcript: %s", transcript[:200])

    # Extract structured data
    extracted = await extract_health_data(transcript)
    logger.info("Extracted data: %s", extracted)

    return extracted


async def standalone_voice_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle voice notes sent outside the check-in flow."""
    if update.effective_user.id != TELEGRAM_USER_ID:
        return

    # Check if we're already in a check-in conversation
    if context.user_data.get("in_checkin"):
        return  # Let the checkin handler deal with it

    await update.message.reply_text("Processing your voice note...")

    extracted = await process_voice_note(update, context)
    if not extracted:
        await update.message.reply_text(
            "Couldn't extract data from that voice note. Try again?"
        )
        return

    # Store extracted data and write to sheet/supabase
    from bot.services.merger import merge_all_sources
    from bot.services.sheets import SheetsService
    from bot.services.supabase_client import upsert_daily_record, get_daily_record
    from bot.services.whoop import WhoopService
    from datetime import date

    today = date.today()

    # Get existing record
    existing = get_daily_record(today.isoformat()) or {}
    telegram_data = {}  # No button data in standalone mode
    whoop_data = {}  # Don't re-pull Whoop for ad-hoc voice

    record = merge_all_sources(
        telegram_data=telegram_data,
        voice_data=extracted,
        whoop_data=whoop_data,
        target_date=today,
    )

    # If existing record, merge with it
    if existing:
        from bot.models.daily_record import DailyRecord
        existing_record = DailyRecord(
            record_date=today,
            **{k: v for k, v in existing.items() if k not in ("id", "created_at", "updated_at", "date")},
        )
        record = existing_record.merge(record)

    # Write to Supabase
    upsert_daily_record(record.to_supabase_dict())

    # Write to Sheet
    try:
        sheets = SheetsService()
        date_str = sheets.find_row_for_date(today)
        sheets.write_daily_data(date_str, record.to_sheet_row())
        record.sheet_synced = True
        upsert_daily_record(record.to_supabase_dict())
    except Exception as e:
        logger.error("Sheet write failed: %s", e)

    # Confirm
    summary_parts = []
    for key, val in extracted.items():
        if val is not None:
            summary_parts.append(f"{key}: {val}")

    await update.message.reply_text(
        f"Updated from voice note:\n" + "\n".join(f"  {p}" for p in summary_parts)
    )
