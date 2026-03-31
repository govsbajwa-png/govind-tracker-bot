# Govind Daily Tracker Bot

A Telegram bot that auto-fills your daily health tracker Google Sheet by combining Whoop biometric data with daily check-ins via inline buttons and voice notes.

## What It Does

- Sends a daily evening check-in on Telegram (8 PM by default)
- Collects subjective metrics via inline buttons (energy, stress, readiness, etc.)
- Accepts voice notes — transcribes and extracts structured data automatically
- Pulls objective data from Whoop (resting HR, HRV, sleep, workouts, steps)
- Writes everything to the correct row in your Google Sheet
- Stores data in Supabase for future dashboard use

## Setup Guide

### Step 1: Create Telegram Bot

1. Open Telegram, message [@BotFather](https://t.me/botfather)
2. Send `/newbot`, choose a name and username
3. Copy the bot token → this is your `TELEGRAM_BOT_TOKEN`
4. Message [@userinfobot](https://t.me/userinfobot) → copy your numeric ID → `TELEGRAM_USER_ID`

### Step 2: Create Whoop Developer App

1. Go to [developer-dashboard.whoop.com](https://developer-dashboard.whoop.com)
2. Sign in with your Whoop account
3. Create a team (first time only)
4. Create a new app:
   - **Name**: Govind Tracker Bot
   - **Redirect URI**: `http://localhost:8080/oauth/callback`
   - **Scopes**: `read:cycles`, `read:recovery`, `read:sleep`, `read:workouts`, `offline`
5. Copy Client ID → `WHOOP_CLIENT_ID`
6. Copy Client Secret → `WHOOP_CLIENT_SECRET`

### Step 3: Create Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create or select a project
3. Enable the **Google Sheets API**
4. Go to **IAM & Admin → Service Accounts** → Create service account
5. Download the JSON key file
6. Base64 encode it:
   ```bash
   base64 -i path/to/credentials.json | tr -d '\n'
   ```
7. Copy the encoded string → `GOOGLE_SHEETS_CREDENTIALS`
8. **Share your Google Sheet** with the service account email (found in the JSON key file) as **Editor**

### Step 4: Get API Keys

1. **Groq** (voice transcription): Sign up at [console.groq.com](https://console.groq.com) → Create API key → `GROQ_API_KEY`
2. **Anthropic** (data extraction): Get key from [console.anthropic.com](https://console.anthropic.com) → `ANTHROPIC_API_KEY`

### Step 5: Create Supabase Project

1. Go to [supabase.com](https://supabase.com) → New project
2. In the SQL Editor, run:

```sql
CREATE TABLE daily_records (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    weight_kg FLOAT,
    resting_hr INT,
    hrv_rmssd FLOAT,
    water_liters FLOAT,
    body_fat_pct FLOAT,
    session_performed TEXT,
    strength_rating INT CHECK (strength_rating BETWEEN 1 AND 10),
    cardio_duration_min INT,
    daily_steps INT,
    morning_readiness INT CHECK (morning_readiness BETWEEN 1 AND 10),
    energy INT CHECK (energy BETWEEN 1 AND 10),
    hunger INT CHECK (hunger BETWEEN 1 AND 10),
    stress INT CHECK (stress BETWEEN 1 AND 10),
    illness BOOLEAN DEFAULT FALSE,
    digestion_issue TEXT DEFAULT 'None',
    bed_time TIME,
    sleep_duration_minutes INT,
    deep_rem_minutes INT,
    stuck_to_plan BOOLEAN,
    whoop_synced BOOLEAN DEFAULT FALSE,
    sheet_synced BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE conversation_memory (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE whoop_tokens (
    id INT DEFAULT 1 PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

3. Go to **Settings → API** → Copy:
   - Project URL → `SUPABASE_URL`
   - Service role key (under `service_role`) → `SUPABASE_KEY`

### Step 6: Deploy to Railway

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add all environment variables (see `.env.example`)
4. Railway will auto-detect the `Procfile` and deploy

### Step 7: Authorize Whoop (One-Time)

1. Run the bot locally first:
   ```bash
   cp .env.example .env
   # Fill in all values in .env
   pip install -r requirements.txt
   python -m bot.main
   ```
2. Open Telegram → message your bot → send `/setup_whoop`
3. Click the OAuth link → log into Whoop → grant access
4. Copy the callback URL from your browser → paste it back to the bot
5. Bot stores tokens in Supabase — Railway deployment will use them automatically

## Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message + setup guide |
| `/checkin` | Start the evening check-in flow |
| `/status` | Show what's been logged today |
| `/setup_whoop` | One-time Whoop authorization |
| `/help` | Show commands |

## Voice Notes

Send a voice note anytime (during check-in or standalone):
> "Energy was a 7, stress 3, readiness 8, weight 68.2, drank 3 liters"

The bot transcribes it, extracts the data, and updates your sheet.

## Ad-Hoc Updates

Text the bot anytime to update specific fields:
> "weight was actually 68.5"
> "forgot — had digestion issues today"

## Cost

~$5.22/month total (Railway $5 + Groq ~$0.04 + Claude ~$0.18)
