"""Groq Whisper transcription service for voice messages."""

import asyncio

from groq import Groq

from bot.config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)


async def transcribe_voice(
    audio_bytes: bytes, filename: str = "voice.ogg"
) -> str:
    """Transcribe audio bytes using Groq's distil-whisper-large-v3-en model.

    The Groq client is synchronous, so we run it in an executor
    to avoid blocking the async event loop.
    """
    loop = asyncio.get_running_loop()
    transcript = await loop.run_in_executor(None, _transcribe_sync, audio_bytes, filename)
    return transcript


def _transcribe_sync(audio_bytes: bytes, filename: str) -> str:
    """Synchronous transcription call to Groq."""
    result = client.audio.transcriptions.create(
        model="distil-whisper-large-v3-en",
        file=(filename, audio_bytes),
    )
    return result.text
