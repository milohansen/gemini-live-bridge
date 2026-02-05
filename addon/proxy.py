import asyncio
import os
import socket
import time
from typing import Awaitable, Callable
from aiohttp import web

from intent_tools import HomeAssistantClient
from web import WebHandler
from session import GeminiSession, GEMINI_API_KEY
from logger import logger
from audio import ESP_INPUT_RATE, WEB_INPUT_RATE

# Configuration
UDP_IP = "0.0.0.0"
UDP_PORT = 7000
ESP_RESPONSE_PORT = 7001
SESSION_TIMEOUT_SECONDS = 60  # Close session if no audio from device for 60s


# --- Main Proxy Class ---
class AudioProxy:
    def __init__(self):
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind((UDP_IP, UDP_PORT))
        self.udp_sock.setblocking(False)

        self.ha_client = HomeAssistantClient()
        self.web_handler = WebHandler(
            self
        )  # Note: WebHandler needs updates to work with sessions

        self.sessions = {}  # Map: (ip, port) -> GeminiSession
        self.running = True

        # Web clients are special, we might treat them as a specific "virtual" session later
        self.web_clients = set()
        self.WEB_INPUT_RATE = WEB_INPUT_RATE

        logger.info(f"Listening on UDP {UDP_IP}:{UDP_PORT}")

    async def udp_listener_task(self):
        loop = asyncio.get_running_loop()
        logger.info("UDP Listener started")

        while self.running:
            try:
                data, addr = await loop.sock_recvfrom(self.udp_sock, 4096)

                session = self.get_session_for_client(addr, "bridge")
                await session.process_incoming_audio(data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"UDP Receive Error: {e}")
                await asyncio.sleep(0.1)

    def get_session_for_client(self, client_addr, mode="bridge", token=None):
        session = self.sessions.get(client_addr)

        if not session or not session.running:
            logger.info(f"Creating new session for {client_addr} in '{mode}' mode")

            async def process_return_audio(chunk: bytes):
                # This logic is now part of the session, specific to client type
                if isinstance(client_addr, tuple): # UDP client
                    target_addr = (client_addr[0], ESP_RESPONSE_PORT)
                    loop = asyncio.get_running_loop()
                    max_size = 1024
                    for i in range(0, len(chunk), max_size):
                        sub_chunk = chunk[i : i + max_size]
                        await loop.sock_sendto(self.udp_sock, sub_chunk, target_addr)
                elif client_addr in self.web_clients: # Web client
                    await client_addr.send_bytes(chunk)


            session = GeminiSession(
                client_addr,
                self,
                process_return_audio,
                mode=mode,
                token=token,
                input_rate=ESP_INPUT_RATE if isinstance(client_addr, tuple) else WEB_INPUT_RATE
            )
            self.sessions[client_addr] = session
            session.task = asyncio.create_task(session.run())
        else:
            logger.debug(f"Using existing session for {client_addr}")
            session.update_activity()

        return session

    def remove_session_for_client(self, client_addr):
        if client_addr in self.sessions:
            logger.info(f"Removing session for {client_addr}")
            session = self.sessions.pop(client_addr)
            session.stop()

    async def cleanup_task(self):
        """Periodically removes stale sessions."""
        while self.running:
            await asyncio.sleep(10)
            now = time.time()
            # Iterate copy of keys to avoid modification error
            for addr in list(self.sessions.keys()):
                sess = self.sessions[addr]
                if now - sess.last_activity > SESSION_TIMEOUT_SECONDS:
                    logger.info(f"Session {sess.id} timed out.")
                    sess.running = False
                    if sess.task:
                        sess.task.cancel()
                    # Removal happens in sess.run() finally block

    async def run(self):
        await self.ha_client.get_states()

        tasks = [
            asyncio.create_task(self.udp_listener_task()),
            asyncio.create_task(self.cleanup_task()),
        ]

        # Web Interface Setup
        app = web.Application()
        app.add_routes(
            [
                web.get("/", self.web_handler.index_handler),
                web.get("/ws", self.web_handler.websocket_handler),
                web.post("/tool", self.web_handler.tool_test_handler),
                web.get("/tools", self.web_handler.tool_list_handler),
                web.get("/entities", self.web_handler.entity_list_handler),
                web.post("/entities", self.web_handler.entities_handler),
                web.post("/session", self.web_handler.session_handler),
            ]
        )
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", UDP_PORT)
        await site.start()

        logger.info(f"Web Interface available at http://{UDP_IP}:{UDP_PORT}")

        try:
            # Keep main loop alive
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await runner.cleanup()


if __name__ == "__main__":
    if not GEMINI_API_KEY and os.path.exists("/data/options.json"):
        try:
            import json

            with open("/data/options.json", "r") as f:
                options = json.load(f)
                GEMINI_API_KEY = options.get("gemini_api_key")
        except Exception:
            pass

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not found.")
        exit(1)

    proxy = AudioProxy()
    try:
        asyncio.run(proxy.run())
    except KeyboardInterrupt:
        logger.info("Stopping...")
