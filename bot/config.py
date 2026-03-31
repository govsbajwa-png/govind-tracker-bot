import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


# Telegram
TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = int(_require("TELEGRAM_USER_ID"))

# Whoop
WHOOP_CLIENT_ID = _require("WHOOP_CLIENT_ID")
WHOOP_CLIENT_SECRET = _require("WHOOP_CLIENT_SECRET")
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
WHOOP_REDIRECT_URI = "http://localhost:8080/oauth/callback"
WHOOP_SCOPES = "read:cycles read:recovery read:sleep read:workouts offline"

# Google Sheets (via Apps Script web app — no service account needed)
GOOGLE_APPS_SCRIPT_URL = _require("GOOGLE_APPS_SCRIPT_URL")

# OpenAI (used for both Whisper transcription and GPT extraction)
OPENAI_API_KEY = _require("OPENAI_API_KEY")

# Supabase
SUPABASE_URL = _require("SUPABASE_URL")
SUPABASE_KEY = _require("SUPABASE_KEY")

# Schedule
CHECKIN_HOUR = int(os.getenv("CHECKIN_HOUR", "20"))
CHECKIN_MINUTE = int(os.getenv("CHECKIN_MINUTE", "0"))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))

# Column mapping: sheet column letters for each field
# Row layout: B=Date, C-U = data columns
SHEET_COLUMNS = {
    "weight": "C",
    "resting_hr": "D",
    "hrv": "E",
    "water": "F",
    "body_fat": "G",
    "session": "H",
    "strength": "I",
    "cardio_duration": "J",
    "steps": "K",
    "readiness": "L",
    "energy": "M",
    "hunger": "N",
    "stress": "O",
    "illness": "P",
    "digestion": "Q",
    "bed_time": "R",
    "sleep_duration": "S",
    "deep_rem": "T",
    "plan": "U",
}
