"""Claude Haiku extraction service for parsing health metrics from transcripts."""

import asyncio
import json

import anthropic

from bot.config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EXTRACTION_SYSTEM_PROMPT = (
    "You extract health metrics from voice transcript text. "
    "Return ONLY valid JSON with these fields "
    "(include only fields explicitly mentioned): "
    "readiness (int 1-10), energy (int 1-10), stress (int 1-10), "
    "hunger (int 1-10), strength (int 1-10 or null), illness (bool), "
    "digestion (string: None/Minor/Major), plan (bool), "
    "weight (float or null), water (float or null), "
    "body_fat (float or null), session (string or null)"
)


async def extract_health_data(transcript: str) -> dict:
    """Send a transcript to Claude Haiku and extract structured health data.

    Returns a dict of health metrics, or an empty dict if parsing fails.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _extract_sync, transcript)
    return result


def _extract_sync(transcript: str) -> dict:
    """Synchronous extraction call to Claude Haiku."""
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": transcript}],
    )

    raw_text = message.content[0].text

    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, IndexError, TypeError):
        return {}
