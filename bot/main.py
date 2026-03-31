"""Govind Daily Tracker Bot — Simple conversational bot powered by OpenAI."""

import datetime
import json
import logging
from io import BytesIO

from openai import OpenAI
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

from bot.config import (
    CHECKIN_HOUR, CHECKIN_MINUTE, OPENAI_API_KEY,
    TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, TIMEZONE,
)
from bot.services.supabase_client import (
    get_daily_record, upsert_daily_record,
    get_whoop_tokens, save_whoop_tokens,
    get_memory, save_memory,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

openai_client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are Govind's personal health tracker bot on Telegram. You're friendly, concise, and helpful.

Your main job: collect daily health data through natural conversation and store it.

The fields you track daily:
- weight_kg (morning weight in kg)
- water_liters (water intake in liters)
- body_fat_pct (body fat percentage)
- morning_readiness (1-10 scale)
- energy (1-10 scale)
- stress (1-10 scale)
- hunger (1-10 scale)
- strength_rating (1-10 scale, workout strength)
- illness (true/false)
- digestion_issue (None, Minor, or Major)
- stuck_to_plan (true/false)
- session_performed (workout description, e.g. "push day, cardio")

When the user tells you about their day, mood, workout, or any health metrics, extract the data and include a JSON block in your response like this:
```json
{"energy": 7, "stress": 3, "weight_kg": 68.2}
```

Only include fields that were explicitly mentioned. Don't guess values.

When doing the evening check-in, ask about the fields naturally — don't list them all at once. Ask 2-3 at a time.

For /setup_whoop, explain that Whoop integration needs OAuth setup and provide the authorization URL.

You can also answer questions about their health data if they ask (e.g., "what did I log today?").

Keep responses short and conversational. You're texting, not writing an essay."""


def get_conversation_history(user_id: int) -> list:
    """Load recent conversation history from Supabase."""
    mem = get_memory(f"chat_history_{user_id}")
    if mem and isinstance(mem, dict):
        return mem.get("value", {}).get("messages", [])
    return []


def save_conversation_history(user_id: int, messages: list):
    """Save conversation history, keeping last 20 messages."""
    trimmed = messages[-20:]
    save_memory(f"chat_history_{user_id}", {"messages": trimmed})


def extract_health_data_from_response(response_text: str) -> dict | None:
    """If the AI response contains a ```json block, extract it."""
    if "```json" not in response_text:
        return None
    try:
        start = response_text.index("```json") + 7
        end = response_text.index("```", start)
        json_str = response_text[start:end].strip()
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError):
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle every text message — send to OpenAI, respond conversationally."""
    if update.effective_user.id != TELEGRAM_USER_ID:
        return
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    logger.info("Message from user: %s", user_text[:100])

    # Load conversation history
    history = get_conversation_history(TELEGRAM_USER_ID)

    # Add today's context
    today = datetime.date.today()
    today_record = get_daily_record(today.isoformat())
    today_context = f"Today is {today.strftime('%A, %B %d')}."
    if today_record:
        logged = {k: v for k, v in today_record.items()
                  if v is not None and k not in ("id", "created_at", "updated_at", "date", "whoop_synced", "sheet_synced")}
        if logged:
            today_context += f" Already logged today: {json.dumps(logged)}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + today_context},
        *history,
        {"role": "user", "content": user_text},
    ]

    # Call OpenAI
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        reply = response.choices[0].message.content
    except Exception as e:
        logger.error("OpenAI error: %s", e)
        await update.message.reply_text("Sorry, had a brain fart. Try again?")
        return

    # Clean the JSON block out of the reply before sending to user
    clean_reply = reply
    if "```json" in clean_reply:
        try:
            json_start = clean_reply.index("```json")
            json_end = clean_reply.index("```", json_start + 7) + 3
            clean_reply = clean_reply[:json_start].strip() + "\n" + clean_reply[json_end:].strip()
        except ValueError:
            pass

    # Send reply to user FIRST (most important thing)
    await update.message.reply_text(clean_reply.strip() or "Got it!")

    # Then save stuff in background (non-critical)
    try:
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})
        save_conversation_history(TELEGRAM_USER_ID, history)
    except Exception as e:
        logger.error("Failed to save chat history: %s", e)

    try:
        extracted = extract_health_data_from_response(reply)
        if extracted:
            record_data = {"date": today.isoformat(), **extracted}
            existing = get_daily_record(today.isoformat())
            if existing:
                for k, v in existing.items():
                    if k not in record_data and k not in ("id", "created_at", "updated_at"):
                        record_data[k] = v
            upsert_daily_record(record_data)
            logger.info("Saved health data: %s", extracted)
    except Exception as e:
        logger.error("Failed to save health data: %s", e)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voice notes — transcribe then treat as text."""
    if update.effective_user.id != TELEGRAM_USER_ID:
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    await update.message.reply_text("Listening...")

    # Download audio
    file = await context.bot.get_file(voice.file_id)
    buf = BytesIO()
    await file.download_to_memory(buf)
    audio_bytes = buf.getvalue()

    # Transcribe with Whisper
    try:
        buf2 = BytesIO(audio_bytes)
        buf2.name = "voice.ogg"
        transcript_response = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=buf2,
        )
        transcript = transcript_response.text
        logger.info("Transcript: %s", transcript[:200])
    except Exception as e:
        logger.error("Whisper error: %s", e)
        await update.message.reply_text("Couldn't understand that audio. Try again?")
        return

    # Now treat the transcript as a regular message
    update.message.text = transcript
    await handle_message(update, context)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "Hey! I'm your daily health tracker bot.\n\n"
        "Just talk to me naturally — tell me about your day, your workout, "
        "how you're feeling, and I'll track everything.\n\n"
        "Commands:\n"
        "/checkin — Start evening check-in\n"
        "/status — See today's data\n"
        "/setup_whoop — Connect Whoop\n\n"
        "Or just send me a voice note about your day!"
    )


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        return
    today = datetime.date.today()
    record = get_daily_record(today.isoformat())
    if not record:
        await update.message.reply_text("Nothing logged yet today. Tell me about your day!")
        return

    lines = [f"📊 *{today.strftime('%B %d')}*\n"]
    labels = {
        "weight_kg": "Weight", "resting_hr": "RHR", "hrv_rmssd": "HRV",
        "water_liters": "Water", "morning_readiness": "Readiness",
        "energy": "Energy", "stress": "Stress", "hunger": "Hunger",
        "strength_rating": "Strength", "session_performed": "Session",
        "illness": "Sick", "digestion_issue": "Digestion",
        "stuck_to_plan": "Plan", "daily_steps": "Steps",
        "sleep_duration_minutes": "Sleep", "deep_rem_minutes": "Deep+REM",
    }
    for key, label in labels.items():
        val = record.get(key)
        if val is not None:
            if isinstance(val, bool):
                val = "Yes" if val else "No"
            elif key in ("sleep_duration_minutes", "deep_rem_minutes"):
                h, m = divmod(val, 60)
                val = f"{h}h {m}m"
            lines.append(f"  {label}: {val}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        return
    update.message.text = "Let's do my evening check-in. Ask me about my day."
    await handle_message(update, context)


async def handle_setup_whoop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != TELEGRAM_USER_ID:
        return
    from bot.config import WHOOP_CLIENT_ID, WHOOP_AUTH_URL, WHOOP_REDIRECT_URI, WHOOP_SCOPES
    from urllib.parse import urlencode
    import secrets

    tokens = get_whoop_tokens()
    if tokens and tokens.get("refresh_token"):
        await update.message.reply_text("Whoop is already connected!")
        return

    state = secrets.token_urlsafe(16)
    context.user_data["whoop_state"] = state

    params = {
        "client_id": WHOOP_CLIENT_ID,
        "redirect_uri": WHOOP_REDIRECT_URI,
        "response_type": "code",
        "scope": WHOOP_SCOPES,
        "state": state,
    }
    auth_url = f"{WHOOP_AUTH_URL}?{urlencode(params)}"

    await update.message.reply_text(
        f"Open this link to connect Whoop:\n\n{auth_url}\n\n"
        "After authorizing, you'll be redirected to a localhost page (it'll error — that's fine).\n"
        "Copy the FULL URL from your browser and paste it here."
    )
    context.user_data["awaiting_whoop"] = True


async def scheduled_checkin(context) -> None:
    """Daily evening check-in prompt."""
    await context.bot.send_message(
        chat_id=TELEGRAM_USER_ID,
        text="Hey! Time for your evening check-in. How was your day? "
             "Tell me about your energy, stress, workouts — or just send a voice note.",
    )


def main() -> None:
    logger.info("Starting Govind Tracker Bot")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("checkin", handle_checkin))
    app.add_handler(CommandHandler("setup_whoop", handle_setup_whoop))

    # Voice notes
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # All other text — goes to OpenAI
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule daily check-in
    checkin_time = datetime.time(hour=CHECKIN_HOUR, minute=CHECKIN_MINUTE, tzinfo=TIMEZONE)
    app.job_queue.run_daily(scheduled_checkin, time=checkin_time, name="daily_checkin")
    logger.info("Scheduled daily check-in at %s", checkin_time)

    logger.info("Bot is running. Polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
