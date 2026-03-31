"""Evening check-in conversation handler with inline buttons + voice interrupt."""

import logging
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import TELEGRAM_USER_ID
from bot.handlers.voice import process_voice_note
from bot.models.daily_record import DailyRecord
from bot.services.merger import merge_all_sources
from bot.services.sheets import SheetsService
from bot.services.supabase_client import get_daily_record, upsert_daily_record
from bot.services.whoop import WhoopService

logger = logging.getLogger(__name__)

# Conversation states
READINESS, ENERGY, STRESS, HUNGER, STRENGTH, ILLNESS, DIGESTION, PLAN, QUICK_STATS = range(9)


def _rating_keyboard(include_skip: bool = False) -> InlineKeyboardMarkup:
    """1-10 rating buttons in two rows."""
    row1 = [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=str(i)) for i in range(6, 11)]
    rows = [row1, row2]
    if include_skip:
        rows.append([InlineKeyboardButton("Skip", callback_data="skip")])
    return InlineKeyboardMarkup(rows)


def _yn_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("No", callback_data="no"),
         InlineKeyboardButton("Yes", callback_data="yes")]
    ])


def _digestion_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("None", callback_data="None")],
        [InlineKeyboardButton("Yes - Minor", callback_data="Yes - Minor"),
         InlineKeyboardButton("Yes - Major", callback_data="Yes - Major")],
    ])


def _plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes", callback_data="yes"),
         InlineKeyboardButton("No", callback_data="no")]
    ])


async def _check_auth(update: Update) -> bool:
    user = update.effective_user
    if user and user.id == TELEGRAM_USER_ID:
        return True
    if update.callback_query:
        await update.callback_query.answer("Unauthorized")
    elif update.message:
        await update.message.reply_text("Unauthorized.")
    return False


async def checkin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the check-in flow (from /checkin command or scheduled trigger)."""
    if update.message and not await _check_auth(update):
        return ConversationHandler.END

    context.user_data["in_checkin"] = True
    context.user_data["checkin_data"] = {}

    msg = (
        "Evening check-in! Let's log today.\n"
        "Tap buttons below, or send a voice note anytime to fill everything at once.\n\n"
        "Morning readiness (1-10):"
    )

    if update.message:
        await update.message.reply_text(msg, reply_markup=_rating_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=_rating_keyboard())
    else:
        # Triggered by scheduler — send directly
        await context.bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=msg,
            reply_markup=_rating_keyboard(),
        )

    return READINESS


async def _handle_voice_interrupt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle voice note sent during check-in — extract all fields and finish."""
    await update.message.reply_text("Got your voice note, processing...")

    extracted = await process_voice_note(update, context)
    if not extracted:
        await update.message.reply_text(
            "Couldn't extract data. Let's continue with buttons.\n"
            "Where were we? Send /checkin to restart."
        )
        return ConversationHandler.END

    # Merge voice data with any button data already collected
    context.user_data.setdefault("checkin_data", {})
    voice_data = extracted
    button_data = context.user_data["checkin_data"]

    # Show what was extracted for confirmation
    summary = []
    for key, val in {**voice_data, **button_data}.items():
        if val is not None:
            summary.append(f"  {key}: {val}")

    await update.message.reply_text(
        "Extracted from voice note + buttons:\n" + "\n".join(summary) + "\n\nPulling Whoop data..."
    )

    # Finalize
    await _finalize_checkin(update, context, button_data, voice_data)
    return ConversationHandler.END


async def readiness_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not await _check_auth(update):
        return ConversationHandler.END

    context.user_data["checkin_data"]["readiness"] = int(query.data)
    await query.edit_message_text(f"Readiness: {query.data}\n\nEnergy level (1-10):")
    await query.message.reply_text("Energy level (1-10):", reply_markup=_rating_keyboard())
    return ENERGY


async def energy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["checkin_data"]["energy"] = int(query.data)
    await query.edit_message_text(f"Energy: {query.data}")
    await query.message.reply_text("Stress level (1-10):", reply_markup=_rating_keyboard())
    return STRESS


async def stress_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["checkin_data"]["stress"] = int(query.data)
    await query.edit_message_text(f"Stress: {query.data}")
    await query.message.reply_text("Hunger level (1-10):", reply_markup=_rating_keyboard())
    return HUNGER


async def hunger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["checkin_data"]["hunger"] = int(query.data)
    await query.edit_message_text(f"Hunger: {query.data}")
    await query.message.reply_text("Strength rating (1-10, or Skip if no workout):", reply_markup=_rating_keyboard(include_skip=True))
    return STRENGTH


async def strength_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "skip":
        context.user_data["checkin_data"]["strength"] = None
        await query.edit_message_text("Strength: Skipped")
    else:
        context.user_data["checkin_data"]["strength"] = int(query.data)
        await query.edit_message_text(f"Strength: {query.data}")

    await query.message.reply_text("Any illness/sickness?", reply_markup=_yn_keyboard())
    return ILLNESS


async def illness_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    is_ill = query.data == "yes"
    context.user_data["checkin_data"]["illness"] = is_ill
    await query.edit_message_text(f"Illness: {'Yes' if is_ill else 'No'}")
    await query.message.reply_text("Digestion issues?", reply_markup=_digestion_keyboard())
    return DIGESTION


async def digestion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    context.user_data["checkin_data"]["digestion"] = query.data
    await query.edit_message_text(f"Digestion: {query.data}")
    await query.message.reply_text("Stuck to the plan today?", reply_markup=_plan_keyboard())
    return PLAN


async def plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    stuck = query.data == "yes"
    context.user_data["checkin_data"]["plan"] = stuck
    await query.edit_message_text(f"Plan: {'Yes' if stuck else 'No'}")
    await query.message.reply_text(
        "Last one! Weight (kg), water intake (L), body fat %?\n"
        "Type or send a voice note. Example: '68.2 kg, 3L water'"
    )
    return QUICK_STATS


async def quick_stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the free-text or voice response for weight/water/body fat."""
    if not await _check_auth(update):
        return ConversationHandler.END

    text = update.message.text or ""

    # Use Claude to extract the numbers
    from bot.services.extraction import extract_health_data

    extracted = await extract_health_data(text)
    button_data = context.user_data.get("checkin_data", {})

    # Only take weight/water/body_fat from this step
    if extracted.get("weight"):
        button_data["weight"] = extracted["weight"]
    if extracted.get("water"):
        button_data["water"] = extracted["water"]
    if extracted.get("body_fat"):
        button_data["body_fat"] = extracted["body_fat"]

    await update.message.reply_text("Got it! Pulling Whoop data...")

    await _finalize_checkin(update, context, button_data, {})
    return ConversationHandler.END


async def quick_stats_voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle voice note at the quick stats step."""
    extracted = await process_voice_note(update, context)
    button_data = context.user_data.get("checkin_data", {})

    if extracted.get("weight"):
        button_data["weight"] = extracted["weight"]
    if extracted.get("water"):
        button_data["water"] = extracted["water"]
    if extracted.get("body_fat"):
        button_data["body_fat"] = extracted["body_fat"]

    await update.message.reply_text("Got it! Pulling Whoop data...")
    await _finalize_checkin(update, context, button_data, {})
    return ConversationHandler.END


async def _finalize_checkin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    button_data: dict,
    voice_data: dict,
) -> None:
    """Pull Whoop data, merge everything, write to Sheet + Supabase, confirm."""
    today = date.today()

    # Map button_data keys to DailyRecord field names
    telegram_data = {}
    if "readiness" in button_data:
        telegram_data["morning_readiness"] = button_data["readiness"]
    if "energy" in button_data:
        telegram_data["energy"] = button_data["energy"]
    if "stress" in button_data:
        telegram_data["stress"] = button_data["stress"]
    if "hunger" in button_data:
        telegram_data["hunger"] = button_data["hunger"]
    if "strength" in button_data and button_data["strength"] is not None:
        telegram_data["strength_rating"] = button_data["strength"]
    if "illness" in button_data:
        telegram_data["illness"] = button_data["illness"]
    if "digestion" in button_data:
        telegram_data["digestion_issue"] = button_data["digestion"]
    if "plan" in button_data:
        telegram_data["stuck_to_plan"] = button_data["plan"]
    if "weight" in button_data:
        telegram_data["weight_kg"] = button_data["weight"]
    if "water" in button_data:
        telegram_data["water_liters"] = button_data["water"]
    if "body_fat" in button_data:
        telegram_data["body_fat_pct"] = button_data["body_fat"]

    # Map voice extracted data
    voice_mapped = {}
    field_map = {
        "readiness": "morning_readiness",
        "energy": "energy",
        "stress": "stress",
        "hunger": "hunger",
        "strength": "strength_rating",
        "illness": "illness",
        "digestion": "digestion_issue",
        "plan": "stuck_to_plan",
        "weight": "weight_kg",
        "water": "water_liters",
        "body_fat": "body_fat_pct",
        "session": "session_performed",
    }
    for src_key, dest_key in field_map.items():
        if src_key in voice_data and voice_data[src_key] is not None:
            voice_mapped[dest_key] = voice_data[src_key]

    # Pull Whoop data
    whoop_data = {}
    try:
        whoop = WhoopService()
        whoop_data = await whoop.pull_daily_data(today)
        logger.info("Whoop data pulled: %s", whoop_data)
    except Exception as e:
        logger.error("Whoop pull failed: %s", e)

    # Merge all sources
    record = merge_all_sources(telegram_data, voice_mapped, whoop_data, today)

    # Check for existing record and merge
    existing = get_daily_record(today.isoformat())
    if existing:
        existing_record = DailyRecord(
            record_date=today,
            **{k: v for k, v in existing.items() if k not in ("id", "created_at", "updated_at", "date")},
        )
        record = existing_record.merge(record)

    # Write to Supabase
    upsert_daily_record(record.to_supabase_dict())

    # Write to Sheet
    sheet_ok = False
    try:
        sheets = SheetsService()
        date_str = sheets.find_row_for_date(today)
        sheets.write_daily_data(date_str, record.to_sheet_row())
        record.sheet_synced = True
        sheet_ok = True
        upsert_daily_record(record.to_supabase_dict())
    except Exception as e:
        logger.error("Sheet write error: %s", e)

    # Build confirmation message
    lines = ["Today's tracker updated!\n"]

    if record.morning_readiness:
        lines.append(f"  Readiness: {record.morning_readiness}")
    if record.energy:
        lines.append(f"  Energy: {record.energy}")
    if record.stress:
        lines.append(f"  Stress: {record.stress}")
    if record.hunger:
        lines.append(f"  Hunger: {record.hunger}")
    if record.weight_kg:
        lines.append(f"  Weight: {record.weight_kg} kg")
    if record.water_liters:
        lines.append(f"  Water: {record.water_liters}L")
    if record.resting_hr:
        lines.append(f"  RHR: {record.resting_hr} bpm")
    if record.hrv_rmssd:
        lines.append(f"  HRV: {record.hrv_rmssd}ms")
    if record.sleep_duration_minutes:
        h, m = divmod(record.sleep_duration_minutes, 60)
        lines.append(f"  Sleep: {h}h {m}m")
    if record.deep_rem_minutes:
        h, m = divmod(record.deep_rem_minutes, 60)
        lines.append(f"  Deep+REM: {h}h {m}m")
    if record.session_performed:
        lines.append(f"  Session: {record.session_performed}")
    if record.daily_steps:
        lines.append(f"  Steps: {record.daily_steps:,}")

    if not sheet_ok:
        lines.append("\n(Sheet write failed — data saved to DB, will retry)")
    if not whoop_data:
        lines.append("\n(Whoop data unavailable — will retry later)")

    # Send confirmation
    chat_id = TELEGRAM_USER_ID
    if update.message:
        await update.message.reply_text("\n".join(lines))
    elif update.callback_query:
        await update.callback_query.message.reply_text("\n".join(lines))
    else:
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))

    # Cleanup
    context.user_data.pop("in_checkin", None)
    context.user_data.pop("checkin_data", None)


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("in_checkin", None)
    context.user_data.pop("checkin_data", None)
    await update.message.reply_text("Check-in cancelled.")
    return ConversationHandler.END


def build_checkin_conversation() -> ConversationHandler:
    """Build and return the ConversationHandler for check-in flow."""
    voice_filter = filters.VOICE | filters.AUDIO

    return ConversationHandler(
        entry_points=[
            CommandHandler("checkin", checkin_start),
        ],
        states={
            READINESS: [
                CallbackQueryHandler(readiness_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            ENERGY: [
                CallbackQueryHandler(energy_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            STRESS: [
                CallbackQueryHandler(stress_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            HUNGER: [
                CallbackQueryHandler(hunger_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            STRENGTH: [
                CallbackQueryHandler(strength_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            ILLNESS: [
                CallbackQueryHandler(illness_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            DIGESTION: [
                CallbackQueryHandler(digestion_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            PLAN: [
                CallbackQueryHandler(plan_handler),
                MessageHandler(voice_filter, _handle_voice_interrupt),
            ],
            QUICK_STATS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, quick_stats_handler),
                MessageHandler(voice_filter, quick_stats_voice_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_handler),
        ],
        per_user=True,
        per_chat=True,
    )
