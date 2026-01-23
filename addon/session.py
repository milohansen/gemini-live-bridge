import asyncio
from typing import Awaitable, Callable
import os
import time
from google import genai
from google.genai import types, live

from logger import logger
from audio import ESP_OUTPUT_RATE, GEMINI_INPUT_RATE, GEMINI_OUTPUT_RATE, resample_audio
from vad import VAD_CHUNK_SIZE_BYTES, VADWrapper
from intent_tools import get_intent_tools, IntentToolHandler
from device_context import fetch_context_via_http

# Configuration
UDP_IP = "0.0.0.0"
UDP_PORT = 7000
ESP_RESPONSE_PORT = 7001

GEMINI_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY and os.path.exists("/data/options.json"):
    try:
        import json
        with open("/data/options.json", "r") as f:
            options = json.load(f)
            GEMINI_API_KEY = options.get("gemini_api_key")
    except Exception: pass


class GeminiSession:
    def __init__(self, address, proxy_server, send_return_audio: Callable[[bytes], Awaitable[None]]):
        self.address = address  # (IP, Port) tuple
        self.proxy = proxy_server
        self.id = f"{address[0]}:{address[1]}"
        logger.info(f"[{self.id}] Initializing Session for {address}")

        self.send_return_audio = send_return_audio

        self.audio_queue_mic = asyncio.Queue()
        self.audio_queue_speaker: asyncio.Queue[bytes] = asyncio.Queue()
        self.vad_buffer = bytearray()
        self.vad = VADWrapper()

        self.client = genai.Client(
            api_key=GEMINI_API_KEY, http_options={"api_version": "v1alpha"}
        )
        self.tool_handler = IntentToolHandler(self.proxy.ha_client)

        self.ai_is_speaking = False
        self.last_activity = time.time()
        self.running = True
        self.task: asyncio.Task | None = None

    def update_activity(self):
        self.last_activity = time.time()

    async def process_incoming_audio(self, raw_audio, source_rate):
        self.update_activity()

        # 1. Resample
        audio_16k = (
            raw_audio
            if source_rate == GEMINI_INPUT_RATE
            else await asyncio.to_thread(
                resample_audio, raw_audio, source_rate, GEMINI_INPUT_RATE
            )
        )

        # 2. VAD Buffering
        self.vad_buffer.extend(audio_16k)

        # 3. Process Chunks
        while len(self.vad_buffer) >= VAD_CHUNK_SIZE_BYTES:
            chunk = bytes(self.vad_buffer[:VAD_CHUNK_SIZE_BYTES])
            del self.vad_buffer[:VAD_CHUNK_SIZE_BYTES]

            if self.ai_is_speaking:
                prob = await asyncio.to_thread(self.vad.is_speech, chunk)
                if prob > 0.8:
                    logger.debug(f"[{self.id}] Barge-in detected!")
                    await self.audio_queue_mic.put(chunk)
            else:
                await self.audio_queue_mic.put(chunk)

    async def run(self):
        """Main lifecycle for this specific session connection."""
        logger.info(f"[{self.id}] Starting Gemini Session")

        # Determine Context based on IP (Optional: You can add a map here)
        # e.g. "You are in the Kitchen" if self.address[0] == "192.168.1.50"
        context = await fetch_context_via_http()
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

        try:
            async with self.client.aio.live.connect(
                model=GEMINI_MODEL, config=config
            ) as session:
                logger.info(f"[{self.id}] Connected to API")

                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self.sender_task(session))
                    tg.create_task(self.receiver_task(session))
                    tg.create_task(self.speaker_output_task())

        except asyncio.CancelledError:
            logger.info(f"[{self.id}] Session cancelled")
        except Exception as e:
            logger.error(f"[{self.id}] Session Error: {e}")
        finally:
            self.running = False
            # Remove self from proxy registry
            if self.address in self.proxy.sessions:
                del self.proxy.sessions[self.address]
            logger.info(f"[{self.id}] Session Closed")

    async def sender_task(self, session: live.AsyncSession):
        while self.running:
            try:
                chunk = await self.audio_queue_mic.get()
                await session.send_realtime_input(
                    audio={
                        "data": chunk,
                        "mime_type": f"audio/pcm;rate={GEMINI_INPUT_RATE}",
                    }
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.id}] Send Error: {e}")
                break
        self.running = False

    async def receiver_task(self, session: live.AsyncSession):
        while self.running:
            try:
                async for response in session.receive():
                    if response.tool_call:
                        function_responses = []
                        function_calls = response.tool_call.function_calls or []
                        for call in function_calls:
                            result = await self.tool_handler.handle_tool_call(
                                call.name, call.args
                            )
                            function_responses.append(
                                types.FunctionResponse(
                                    name=call.name,
                                    id=call.id,
                                    response={"result": result},
                                )
                            )
                        if function_responses:
                            await session.send_tool_response(
                                function_responses=function_responses
                            )

                    server_content = response.server_content
                    if server_content:
                        if server_content.model_turn:
                            turn_parts = server_content.model_turn.parts or []
                            for part in turn_parts:
                                if part.inline_data:
                                    self.ai_is_speaking = True
                                    audio_24k = part.inline_data.data
                                    audio_48k = await asyncio.to_thread(
                                        resample_audio,
                                        audio_24k,
                                        GEMINI_OUTPUT_RATE,
                                        ESP_OUTPUT_RATE,
                                    )
                                    await self.audio_queue_speaker.put(audio_48k)

                        if server_content.turn_complete:
                            self.ai_is_speaking = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.id}] Receive Error: {e}")
                break
        self.running = False

    async def speaker_output_task(self):
        """Sends audio back to the specific UDP address for this session."""
        # loop = asyncio.get_running_loop()
        while self.running:
            try:
                chunk = await self.audio_queue_speaker.get()
                await self.send_return_audio(chunk)

                # # Send back to specific ESP address
                # target_addr = (self.address[0], ESP_RESPONSE_PORT)

                # max_size = 1024
                # for i in range(0, len(chunk), max_size):
                #     sub_chunk = chunk[i : i + max_size]
                #     await loop.sock_sendto(self.proxy.udp_sock, sub_chunk, target_addr)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[{self.id}] UDP Send Error: {e}")
        self.running = False
