"""Govind Daily Tracker Bot — Entry point."""

import datetime
import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import CHECKIN_HOUR, CHECKIN_MINUTE, TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, TIMEZONE
from bot.handlers.checkin import build_checkin_conversation, checkin_start
from bot.handlers.start import help_handler, start_handler, status_handler
from bot.handlers.setup import setup_whoop_handler
from bot.handlers.voice import standalone_voice_handler
from bot.handlers.adhoc import adhoc_text_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def scheduled_checkin(context) -> None:
    """Send the daily check-in prompt at the scheduled time."""
    logger.info("Triggering scheduled evening check-in")
    from telegram import Update

    # Send the check-in message directly
    keyboard_msg = (
        "Evening check-in! Let's log today.\n"
        "Send /checkin to start, or drop a voice note right now."
    )
    await context.bot.send_message(
        chat_id=TELEGRAM_USER_ID,
        text=keyboard_msg,
    )


async def retry_whoop(context) -> None:
    """Morning retry job: try to fill in any missing Whoop data from yesterday."""
    from datetime import date
    from bot.services.supabase_client import get_daily_record, upsert_daily_record
    from bot.services.whoop import WhoopService
    from bot.services.sheets import SheetsService
    from bot.models.daily_record import DailyRecord

    yesterday = date.today() - datetime.timedelta(days=1)
    record = get_daily_record(yesterday.isoformat())

    if not record or record.get("whoop_synced"):
        return  # Already synced or no record

    logger.info("Retrying Whoop pull for %s", yesterday)
    try:
        whoop = WhoopService()
        whoop_data = await whoop.pull_daily_data(yesterday)
        if not whoop_data:
            return

        # Build updated record
        existing = DailyRecord(
            record_date=yesterday,
            **{k: v for k, v in record.items() if k not in ("id", "created_at", "updated_at", "date")},
        )
        whoop_record = DailyRecord(record_date=yesterday, whoop_synced=True, **whoop_data)
        merged = existing.merge(whoop_record)

        # Update Supabase
        upsert_daily_record(merged.to_supabase_dict())

        # Update Sheet
        sheets = SheetsService()
        date_str = sheets.find_row_for_date(yesterday)
        sheets.write_daily_data(date_str, merged.to_sheet_row())
        merged.sheet_synced = True
        upsert_daily_record(merged.to_supabase_dict())

        logger.info("Whoop retry successful for %s", yesterday)
        await context.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"Updated yesterday's ({yesterday.strftime('%b %d')}) Whoop data.",
        )
    except Exception as e:
        logger.error("Whoop retry failed: %s", e)


def main() -> None:
    """Start the bot."""
    logger.info("Starting Govind Tracker Bot")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers (order matters)
    # 1. Check-in conversation (highest priority for button flow)
    checkin_conv = build_checkin_conversation()
    app.add_handler(checkin_conv)

    # 2. Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("setup_whoop", setup_whoop_handler))

    # 3. Standalone voice notes (outside check-in flow)
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, standalone_voice_handler))

    # 4. Ad-hoc text messages (lowest priority)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, adhoc_text_handler))

    # Schedule daily check-in
    job_queue = app.job_queue
    checkin_time = datetime.time(
        hour=CHECKIN_HOUR,
        minute=CHECKIN_MINUTE,
        tzinfo=TIMEZONE,
    )
    job_queue.run_daily(
        scheduled_checkin,
        time=checkin_time,
        name="daily_checkin",
    )
    logger.info("Scheduled daily check-in at %s", checkin_time)

    # Schedule morning Whoop retry (9 AM)
    retry_time = datetime.time(hour=9, minute=0, tzinfo=TIMEZONE)
    job_queue.run_daily(
        retry_whoop,
        time=retry_time,
        name="whoop_retry",
    )
    logger.info("Scheduled Whoop retry at %s", retry_time)

    # Start polling
    logger.info("Bot is running. Polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
