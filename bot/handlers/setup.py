"""One-time Whoop OAuth setup handler."""

import logging
import secrets
from urllib.parse import urlencode

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from bot.config import (
    TELEGRAM_USER_ID,
    WHOOP_CLIENT_ID,
    WHOOP_CLIENT_SECRET,
    WHOOP_AUTH_URL,
    WHOOP_TOKEN_URL,
    WHOOP_REDIRECT_URI,
    WHOOP_SCOPES,
)
from bot.services.supabase_client import save_whoop_tokens, get_whoop_tokens

logger = logging.getLogger(__name__)


async def setup_whoop_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /setup_whoop — guide user through OAuth flow."""
    if update.effective_user.id != TELEGRAM_USER_ID:
        return

    # Check if already authorized
    tokens = get_whoop_tokens()
    if tokens and tokens.get("refresh_token"):
        await update.message.reply_text(
            "Whoop is already connected! Your tokens are stored.\n"
            "To re-authorize, send /reauth_whoop"
        )
        return

    state = secrets.token_urlsafe(16)
    context.user_data["whoop_oauth_state"] = state

    params = {
        "client_id": WHOOP_CLIENT_ID,
        "redirect_uri": WHOOP_REDIRECT_URI,
        "response_type": "code",
        "scope": WHOOP_SCOPES,
        "state": state,
    }
    auth_url = f"{WHOOP_AUTH_URL}?{urlencode(params)}"

    await update.message.reply_text(
        "To connect Whoop, follow these steps:\n\n"
        f"1. Open this URL in your browser:\n{auth_url}\n\n"
        "2. Log in to Whoop and grant access\n\n"
        "3. You'll be redirected to localhost (it will show an error — that's OK)\n\n"
        "4. Copy the FULL URL from your browser's address bar and paste it here\n\n"
        "The URL will look like: http://localhost:8080/oauth/callback?code=xxx&state=yyy"
    )
    context.user_data["awaiting_whoop_callback"] = True


async def handle_whoop_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Check if a message is a Whoop OAuth callback URL. Returns True if handled."""
    if not context.user_data.get("awaiting_whoop_callback"):
        return False

    text = (update.message.text or "").strip()
    if "oauth/callback" not in text and "code=" not in text:
        return False

    # Parse the callback URL
    from urllib.parse import urlparse, parse_qs

    try:
        parsed = urlparse(text)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
    except Exception:
        await update.message.reply_text("Couldn't parse that URL. Please try again.")
        return True

    if not code:
        await update.message.reply_text("No authorization code found in the URL. Please try again.")
        return True

    # Verify state
    expected_state = context.user_data.get("whoop_oauth_state")
    if state and expected_state and state != expected_state:
        await update.message.reply_text("State mismatch — possible CSRF. Please run /setup_whoop again.")
        context.user_data.pop("awaiting_whoop_callback", None)
        return True

    # Exchange code for tokens
    await update.message.reply_text("Exchanging authorization code for tokens...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                WHOOP_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": WHOOP_CLIENT_ID,
                    "client_secret": WHOOP_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": WHOOP_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            token_data = resp.json()
    except Exception as e:
        logger.error("Token exchange failed: %s", e)
        await update.message.reply_text(f"Token exchange failed: {e}\nPlease run /setup_whoop again.")
        context.user_data.pop("awaiting_whoop_callback", None)
        return True

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)

    if not access_token or not refresh_token:
        await update.message.reply_text(
            "Received tokens but missing access or refresh token. "
            "Make sure 'offline' scope is selected in your Whoop app."
        )
        context.user_data.pop("awaiting_whoop_callback", None)
        return True

    # Calculate expiry
    from datetime import datetime, timedelta, timezone

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Save tokens
    save_whoop_tokens(access_token, refresh_token, expires_at.isoformat())

    context.user_data.pop("awaiting_whoop_callback", None)
    context.user_data.pop("whoop_oauth_state", None)

    await update.message.reply_text(
        "Whoop connected successfully! Your tokens are stored securely.\n\n"
        "The bot will now automatically pull your Whoop data during check-ins."
    )
    return True
