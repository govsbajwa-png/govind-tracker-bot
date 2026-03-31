"""OpenAI Whisper transcription service for voice messages."""

import asyncio
from io import BytesIO

from openai import OpenAI

from bot.config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)


def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe audio bytes using OpenAI Whisper.

    Synchronous — callers should await via run_in_executor if needed.
    """
    buf = BytesIO(audio_bytes)
    buf.name = filename
    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
    )
    return result.text


async def transcribe_voice_async(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Async wrapper for transcription."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, transcribe_voice, audio_bytes, filename)
