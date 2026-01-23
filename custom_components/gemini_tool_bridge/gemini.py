"""Gemini session management."""

import logging
import traceback
import datetime

from homeassistant.core import HomeAssistant
import google.genai as genai
from google.genai import types

from context import (
    generate_context_from_ha,
)
from intent_tools import get_intent_tools

_LOGGER = logging.getLogger(__name__)


async def generate_token(client: genai.Client, hass: HomeAssistant) -> types.AuthToken:

    _LOGGER.info("Received request for a new Gemini session")

    try:
        # 1. Generate context and tools
        context = await generate_context_from_ha(hass)
        base_instruction = "You are a helpful and friendly AI assistant. Be concise."
        full_system_instruction = f"{base_instruction}\n\n{context}"

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            tools=get_intent_tools(),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=full_system_instruction)],
                role="user",
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                turn_coverage=types.TurnCoverage.TURN_INCLUDES_ALL_INPUT
            ),
        )

        # 2. Create ephemeral token

        now = datetime.datetime.now(tz=datetime.timezone.utc)

        token = client.auth_tokens.create(
            uses=10,
            expire_time=now + datetime.timedelta(hours=20),
            new_session_expire_time=now + datetime.timedelta(hours=1),
            http_options={"api_version": "v1alpha"},
            live_connect_constraints={
                "model": "gemini-2.5-flash-native-audio-preview-12-2025",
                "config": config,
            },
        )

        return token

    except Exception as e:
        _LOGGER.error(f"Error creating session: {e}")
        error_trace = traceback.format_exc()
        _LOGGER.error(f"Traceback: {error_trace}")
        raise e
