"""OpenAI GPT extraction service for parsing health metrics from transcripts."""

import asyncio
import json

from openai import OpenAI

from bot.config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

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


def _extract_sync(transcript: str) -> dict:
    """Synchronous extraction call to GPT-4o-mini."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ],
        max_tokens=512,
        temperature=0,
    )
    raw_text = response.choices[0].message.content
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, IndexError, TypeError):
        return {}


async def extract_health_data(transcript: str) -> dict:
    """Async wrapper — extract structured health data from transcript."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract_sync, transcript)
