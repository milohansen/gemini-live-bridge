import asyncio
import os
import socket
import logging
import numpy as np
from scipy import signal as scipy_signal
from google import genai
from google.genai import types
import onnxruntime
from aiohttp import web, WSMsgType

from tools import get_tools, ToolHandler, HomeAssistantClient
from device_context import STATIC_DEVICE_CONTEXT
from web import WebHandler

# Configuration
UDP_IP = "0.0.0.0"
UDP_PORT = 7000
ESP_RESPONSE_PORT = 7001

GEMINI_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Audio Config
ESP_INPUT_RATE = 32000  # ESP32 P4 Native
GEMINI_INPUT_RATE = 16000
GEMINI_OUTPUT_RATE = 24000
ESP_OUTPUT_RATE = 48000
WEB_INPUT_RATE = 48000  # Standard browser mic rate (approx)

# VAD Config
VAD_MODEL_PATH = "silero_vad.onnx"
# Silero VAD works best with chunks of 512, 1024, or 1536 samples (at 16kHz)
VAD_CHUNK_SIZE_SAMPLES = 512
VAD_CHUNK_SIZE_BYTES = VAD_CHUNK_SIZE_SAMPLES * 2  # 16-bit audio = 2 bytes/sample

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VADWrapper:
    def __init__(self):
        if not os.path.exists(VAD_MODEL_PATH):
            logger.info("Downloading Silero VAD model (V5)...")
            import urllib.request

            urllib.request.urlretrieve(
                "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx",
                VAD_MODEL_PATH,
            )

        # Suppress onnxruntime warnings
        sess_options = onnxruntime.SessionOptions()
        sess_options.log_severity_level = 3
        self.session = onnxruntime.InferenceSession(VAD_MODEL_PATH, sess_options)
        self.reset_states()

    def reset_states(self):
        # Silero VAD V5 uses a single state tensor of shape (2, 1, 128)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def is_speech(self, audio_chunk_16k):
        audio_int16 = np.frombuffer(audio_chunk_16k, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Protect against empty or tiny chunks
        if len(audio_float32) < 32:
            return 0.0

        input_data = {
            "input": audio_float32[np.newaxis, :],
            "sr": np.array([16000], dtype=np.int64),
            "state": self._state,
        }

        # Run inference: returns [output, state]
        out, state = self.session.run(None, input_data)
        self._state = state
        return out[0][0]


class AudioProxy:
    def __init__(self):
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind((UDP_IP, UDP_PORT))
        self.udp_sock.setblocking(False)

        self.client = genai.Client(
            api_key=GEMINI_API_KEY, http_options={"api_version": "v1alpha"}
        )

        self.ha_client = HomeAssistantClient()
        self.tool_handler = ToolHandler(self.ha_client)
        self.web_handler = WebHandler(self)

        self.esp_address = None
        self.running = True

        self.audio_queue_mic = asyncio.Queue()
        self.audio_queue_speaker = asyncio.Queue()
        self.vad_buffer = bytearray()  # Buffer for incoming audio

        self.vad = VADWrapper()

        self.ai_is_speaking = False
        self.connection_active = asyncio.Event()

        self.web_clients = set()

        self.WEB_INPUT_RATE = WEB_INPUT_RATE

        logger.info(f"Listening on UDP {UDP_IP}:{UDP_PORT}")

    def resample_audio(self, audio_data, src_rate, dst_rate):
        if src_rate == dst_rate:
            return audio_data

        audio_np = np.frombuffer(audio_data, dtype=np.int16)
        num_samples = int(len(audio_np) * dst_rate / src_rate)
        resampled_np = scipy_signal.resample(audio_np, num_samples)
        return resampled_np.astype(np.int16).tobytes()

    async def send_stop_command(self):
        """Sends a command to ESP32 to stop streaming"""
        if self.esp_address:
            try:
                loop = asyncio.get_running_loop()
                stop_msg = b"GEMINI_STOP"
                target_port = ESP_RESPONSE_PORT
                target_addr = (self.esp_address[0], target_port)
                await loop.sock_sendto(self.udp_sock, stop_msg, target_addr)
                logger.info("Sent STOP command to ESP32")
            except Exception as e:
                logger.error(f"Failed to send STOP command: {e}")

    async def process_incoming_audio(self, raw_audio, source_rate):
        """Shared logic for processing audio from UDP or Web"""
        # 1. Resample to 16k
        audio_16k = (
            raw_audio
            if source_rate == GEMINI_INPUT_RATE
            else await asyncio.to_thread(
                self.resample_audio, raw_audio, source_rate, GEMINI_INPUT_RATE
            )
        )

        # 2. Add to VAD buffer
        self.vad_buffer.extend(audio_16k)

        # 3. Process in fixed-size chunks
        while len(self.vad_buffer) >= VAD_CHUNK_SIZE_BYTES:
            chunk = bytes(self.vad_buffer[:VAD_CHUNK_SIZE_BYTES])
            del self.vad_buffer[:VAD_CHUNK_SIZE_BYTES]

            # Gating Logic
            if self.ai_is_speaking:
                prob = await asyncio.to_thread(self.vad.is_speech, chunk)
                if prob > 0.8:
                    logger.debug("Barge-in detected!")
                    await self.audio_queue_mic.put(chunk)
            else:
                await self.audio_queue_mic.put(chunk)

    async def udp_listener_task(self):
        loop = asyncio.get_running_loop()
        logger.info("UDP Listener started")

        while self.running:
            try:
                data, addr = await loop.sock_recvfrom(self.udp_sock, 4096)

                if not self.esp_address:
                    logger.info(f"Connection established from ESP32 at {addr}")
                    self.esp_address = addr
                    self.connection_active.set()
                elif self.esp_address[0] != addr[0]:
                    self.esp_address = addr
                    self.connection_active.set()

                # --- Monitor Logic ---
                # Forward ESP32 audio to connected Web Clients for monitoring.
                # Since the browser expects 48kHz (set in playAudio), we must resample.
                if self.web_clients:
                    audio_48k_monitor = await asyncio.to_thread(
                        self.resample_audio,
                        data,
                        ESP_INPUT_RATE,
                        48000,  # Web Client Rate
                    )
                    for ws in list(self.web_clients):
                        if not ws.closed:
                            try:
                                await ws.send_bytes(audio_48k_monitor)
                            except Exception as e:
                                logger.error(f"Web Send Error: {e}")

                await self.process_incoming_audio(data, ESP_INPUT_RATE)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"UDP Receive Error: {e}")
                await asyncio.sleep(0.1)

        logger.info("UDP Listener stopped")

    async def udp_sender_task(self):
        loop = asyncio.get_running_loop()
        logger.info("UDP Sender started")
        while self.running:
            try:
                chunk = await self.audio_queue_speaker.get()
                # logger.debug(f"UDP Packet sending: {len(chunk)} bytes")
                if self.esp_address:
                    target_port = ESP_RESPONSE_PORT
                    target_addr = (self.esp_address[0], target_port)

                    max_size = 1024
                    for i in range(0, len(chunk), max_size):
                        sub_chunk = chunk[i : i + max_size]
                        await loop.sock_sendto(self.udp_sock, sub_chunk, target_addr)

                if self.web_clients:
                    for ws in list(self.web_clients):
                        if not ws.closed:
                            await ws.send_bytes(chunk)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"UDP Send Error: {e}")

    async def gemini_session_handler(self):
        logger.info("Waiting for ESP32 connection before connecting to Gemini...")
        await self.connection_active.wait()

        base_instruction = "You are a helpful and friendly AI assistant. Be concise."
        full_system_instruction = f"{base_instruction}\n\n{STATIC_DEVICE_CONTEXT}"

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            tools=get_tools(),
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=full_system_instruction)],
                role="user",
            ),
            # proactivity=types.ProactivityConfig(proactive_audio=True),
            # enable_affective_dialog=True,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                        # voice_name="Laomedeia"
                    )
                )
            ),
            output_audio_transcription=types.AudioTranscriptionConfig,
            input_audio_transcription=types.AudioTranscriptionConfig,
            realtime_input_config=types.RealtimeInputConfig(
                turn_coverage="TURN_INCLUDES_ALL_INPUT"
            ),
        )

        logger.info(f"Connecting to Gemini Live ({GEMINI_MODEL})...")

        try:
            async with self.client.aio.live.connect(
                model=GEMINI_MODEL, config=config
            ) as session:
                logger.info("Connected to Gemini API!")

                async with asyncio.TaskGroup() as tg:
                    tg.create_task(self.gemini_sender_task(session))
                    tg.create_task(self.gemini_receiver_task(session))

        except Exception as e:
            logger.error(f"Gemini Session Error: {e}")
            # Clear queues to prevent stale audio/state
            self.vad.reset_states()
            self.vad_buffer.clear()
            while not self.audio_queue_mic.empty():
                self.audio_queue_mic.get_nowait()
            raise

    async def gemini_sender_task(self, session):
        while self.running:
            try:
                chunk = await self.audio_queue_mic.get()
                await session.send_realtime_input(
                    audio={
                        "data": chunk,
                        "mime_type": f"audio/pcm;rate={GEMINI_INPUT_RATE}",
                    }
                )
                # logger.debug("Sent audio chunk to Gemini")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gemini Send Error: {e}")
                raise

    async def gemini_receiver_task(self, session):
        while self.running:
            try:
                async for response in session.receive():
                    # 1. Handle Tool Calls
                    if response.tool_call:
                        function_calls = response.tool_call.function_calls
                        function_responses = []

                        for call in function_calls:
                            # Execute the tool via Home Assistant
                            result = await self.tool_handler.handle_tool_call(
                                call.name, call.args
                            )

                            # Create response object
                            function_responses.append(
                                types.FunctionResponse(
                                    name=call.name,
                                    id=call.id,
                                    response={"result": result},
                                )
                            )

                        # Send responses back to Gemini
                        if function_responses:
                            await session.send_tool_response(
                                function_responses=function_responses
                            )

                    server_content = response.server_content
                    if not server_content:
                        continue

                    if server_content.output_transcription:
                        logger.info(
                            f"Transcript (Output): {server_content.output_transcription.text}"
                        )
                    if server_content.input_transcription:
                        logger.info(
                            f"Transcript (Input): {server_content.input_transcription.text}"
                        )

                    if server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data and isinstance(
                                part.inline_data.data, bytes
                            ):
                                self.ai_is_speaking = True
                                logger.debug("AI is speaking")
                                audio_24k = part.inline_data.data

                                audio_48k = await asyncio.to_thread(
                                    self.resample_audio,
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
                logger.error(f"Gemini Receive Error: {e}")
                self.ai_is_speaking = False
                await self.send_stop_command()  # Tell ESP32 to stop
                raise

    async def run(self):
        # Start UDP tasks
        udp_listener = asyncio.create_task(self.udp_listener_task())
        udp_sender = asyncio.create_task(self.udp_sender_task())

        # Setup Web Server
        app = web.Application()
        app.add_routes(
            [
                web.get("/", self.web_handler.index_handler),
                web.get("/ws", self.web_handler.websocket_handler),
                web.post("/tool", self.web_handler.tool_test_handler),
                web.get("/tools", self.web_handler.tool_list_handler),
            ]
        )
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", UDP_PORT)
        await site.start()

        await self.ha_client.get_states()

        logger.info(f"Web Interface available at http://{UDP_IP}:{UDP_PORT}")

        while self.running:
            try:
                await self.gemini_session_handler()
            except Exception:
                logger.info("Gemini session ended. Reconnecting in 2 seconds...")
                await asyncio.sleep(2)

        await runner.cleanup()
        udp_listener.cancel()
        udp_sender.cancel()


if __name__ == "__main__":
    if not GEMINI_API_KEY and os.path.exists("/data/options.json"):
        try:
            import json

            with open("/data/options.json", "r") as f:
                options = json.load(f)
                GEMINI_API_KEY = options.get("gemini_api_key")
        except Exception as e:
            logger.error(f"Failed to read options.json: {e}")

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found.")
        exit(1)

    proxy = AudioProxy()
    try:
        asyncio.run(proxy.run())
    except KeyboardInterrupt:
        logger.info("Stopping...")
