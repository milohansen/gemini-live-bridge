"""OpenAI session management."""

import logging
import traceback
import datetime

import asyncio
from agents.realtime import RealtimeAgent, RealtimeRunner, RealtimeRunConfig, RealtimeSessionModelSettings, RealtimeInputAudioTranscriptionConfig, RealtimeTurnDetectionConfig

from homeassistant.core import HomeAssistant
from openai import OpenAI

from .context import (
    generate_context_from_ha,
)
from .intent_tools import get_intent_tools

_LOGGER = logging.getLogger(__name__)


def get_client(api_key: str) -> OpenAI:
    """Create a Gemini client with the provided API key."""
    client = OpenAI(
        api_key=api_key,
    )
    return client


async def generate_config(hass: HomeAssistant) -> RealtimeRunConfig:
    agent = RealtimeAgent(
        name="Assistant",
        instructions="You are a helpful voice assistant. Keep your responses conversational and friendly.",
    )

    try:
        # 1. Generate context and tools
        context = await generate_context_from_ha(hass)
        base_instruction = "You are a helpful and friendly AI assistant. Be concise."
        full_system_instruction = f"{base_instruction}\n\n{context}"

        config = RealtimeRunConfig(
            model_settings=RealtimeSessionModelSettings(
                model_name="gpt-realtime",
                voice="marin",
                modalities=["audio"],
                input_audio_transcription=RealtimeInputAudioTranscriptionConfig(model="gpt-4o-mini-transcribe"),
                turn_detection=RealtimeTurnDetectionConfig(type="semantic_vad", interrupt_response=True),
            ),
        )

        return config

    except Exception as e:
        _LOGGER.error(f"Error creating config: {e}")
        error_trace = traceback.format_exc()
        _LOGGER.error(f"Traceback: {error_trace}")
        raise e




async def generate_token(client: genai.Client, hass: HomeAssistant) -> types.AuthToken:

    _LOGGER.info("Received request for a new Gemini session")

    try:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        token = client.auth_tokens.create(
            config={
                "uses": 10,
                "expire_time": now + datetime.timedelta(hours=20),
                "new_session_expire_time": now + datetime.timedelta(hours=1),
                "http_options": {"api_version": "v1alpha"},
                "live_connect_constraints": {
                    "model": "gemini-2.5-flash-native-audio-preview-12-2025",
                    "config": await generate_config(hass),
                },
            }
        )

        return token

    except Exception as e:
        _LOGGER.error(f"Error creating session: {e}")
        error_trace = traceback.format_exc()
        _LOGGER.error(f"Traceback: {error_trace}")
        raise e
    
