from html import entities
import logging
import traceback
from aiohttp import web, WSMsgType, ClientSession

# from audio import WEB_INPUT_RATE
from context import get_context, HA_URL, HA_TOKEN
from intent_tools import IntentToolHandler, get_intent_tools

logger = logging.getLogger(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Gemini Live Proxy</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
        h1, h3, p { text-align: center; }
        .section { border: 1px solid #ccc; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>Gemini Live Proxy</h1>

    <div class="section">
        <h3>Server did not load the HTML file.</h3>
    </div>
</body>
</html>
"""

with open("app/web.html", "r") as f:
    INDEX_HTML = f.read()


class WebHandler:
    def __init__(self, proxy):
        self.proxy = proxy
        self.tool_handler = IntentToolHandler(self.proxy.ha_client)

    async def index_handler(self, request: web.Request):
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def session_handler(self, request: web.Request):
        """Proxy the session request to the Home Assistant component."""
        try:

            url = f"{HA_URL}/gemini_live/session"
            headers = {
                "Authorization": f"Bearer {HA_TOKEN}",
                "Content-Type": "application/json",
            }

            async with ClientSession() as session:
                async with session.post(url, headers=headers) as resp:
                    if resp.status == 200:
                        session_data = await resp.json()
                        return web.json_response(session_data)
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to create session: {resp.status} {error_text}")
                        return web.json_response({"success": False, "error": error_text}, status=resp.status)

        except Exception as e:
            logger.error(f"session_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def config_handler(self, request: web.Request):
        """Proxy the session request to the Home Assistant component."""
        try:

            url = f"{HA_URL}/gemini_live/config"
            headers = {
                "Authorization": f"Bearer {HA_TOKEN}",
            }

            async with ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return web.Response(text=str(await resp.text()))
                    else:
                        error_text = await resp.text()
                        raise Exception(f"Failed to get config: {resp.status} {error_text}")

        except Exception as e:
            logger.error(f"session_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def websocket_handler(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.proxy.web_clients.add(ws)
        logger.info("Web Client Connected")

        try:
            # First message is configuration
            config_msg = await ws.receive_json()
            mode = config_msg.get("mode", "bridge")
            token = config_msg.get("token")

            # Use the ws object itself as the key for web clients
            session = self.proxy.get_session_for_client(ws, mode, token)

            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    await session.process_incoming_audio(msg.data)
                elif msg.type == WSMsgType.TEXT:
                     logger.warning(f"Received unexpected text message from web client: {msg.data}")
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"Websocket connection closed with exception {ws.exception()}")
                    break
        finally:
            self.proxy.remove_session_for_client(ws)
            self.proxy.web_clients.remove(ws)
            logger.info("Web Client Disconnected")

        return ws

    async def tool_test_handler(self, request: web.Request):
        """Handle manual tool execution requests."""
        try:
            data = await request.json()
            name = data.get("name")
            args = data.get("args", {})
            result = await self.tool_handler.handle_tool_call(name, args)
            return web.Response(text=str(result))
        except Exception as e:
            return web.Response(text=f"Error: {e}", status=500)
        
    async def tool_list_handler(self, request: web.Request):
        """List all available tools."""
        try:
            tools_data = []
            tool_objs = get_intent_tools()
            for tool in tool_objs:
                funcs = tool.function_declarations or []
                for func in funcs:
                     tools_data.append({
                         "name": func.name,
                         "description": func.description,
                         "parameters": func.parameters_json_schema
                     })
            
            return web.json_response({"tools": tools_data})
        except Exception as e:
            logger.error(f"tool_list_handler error: {e}")
            return web.Response(text=f"Error: {e}", status=500)
        
    async def entity_list_handler(self, request: web.Request):
        """List all available entities."""
        try:
            entities = await get_context(raw=True)
            return web.json_response(entities)
        except Exception as e:
            logger.error(f"entity_list_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.Response(text=f"Error: {e}", status=500)
        
    async def entities_handler(self, request: web.Request):
        """List all available entities (grouped context)."""
        try:
            entities = await get_context(raw=False)
            return web.Response(text=str(entities))
        except Exception as e:
            logger.error(f"entities_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.Response(text=f"Error: {e}", status=500)