import datetime
from device_context import generate_device_context
from google.genai import types
import logging
import os
from aiohttp import ClientSession

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.getenv('SUPERVISOR_TOKEN')

DEVICE_CONTEXT_PREFIX = "Static Context: An overview of the areas and the devices in this smart home:"

# --- Home Assistant Client ---
class HomeAssistantClient:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json",
        }
        self.entities = {}  # Cache for name resolution
        self.device_context = DEVICE_CONTEXT_PREFIX

    async def get_states(self):
        """Fetch all states from Home Assistant."""
        if not HA_TOKEN:
            logger.error("SUPERVISOR_TOKEN not found. Cannot fetch HA states.")
            return []
        
        async with ClientSession() as session:
            try:
                async with session.get(f"{HA_URL}/states", headers=self.headers) as resp:
                    if resp.status == 200:
                        states = await resp.json()
                        # Update name cache
                        for state in states:
                            if "friendly_name" in state.get("attributes", {}):
                                self.entities[state["attributes"]["friendly_name"].lower()] = state["entity_id"]
                                self.device_context += f"\n- names: {state['attributes']['friendly_name']}\n  domain: {state['entity_id'].split('.')[0]}\n"
                        logger.info(f"Fetched {len(states)} states from Home Assistant.")
                        return states
                    else:
                        logger.error(f"Failed to fetch states: [{resp.status}] {await resp.text()}")
                        return []
            except Exception as e:
                logger.error(f"HA API Error: {e}")
                return []

    async def get_state(self, entity_id):
        """Fetch all states from Home Assistant."""
        if not HA_TOKEN:
            logger.error("SUPERVISOR_TOKEN not found. Cannot fetch HA states.")
            return []
        
        async with ClientSession() as session:
            try:
                async with session.get(f"{HA_URL}/states/{entity_id}", headers=self.headers) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Failed to fetch state for '{entity_id}': [{resp.status}] {await resp.text()}")
                        return []
            except Exception as e:
                logger.error(f"HA API Error: {e}")
                return []

    async def call_service(self, domain, service, service_data=None):
        """Call a service in Home Assistant."""
        if not HA_TOKEN:
            logger.error("SUPERVISOR_TOKEN not found.")
            return "Error: No API Token"

        url = f"{HA_URL}/services/{domain}/{service}"
        payload = service_data or {}
        
        # Resolve 'name' to 'entity_id' if provided and not already an ID
        if "name" in payload:
            name = payload.pop("name")
            if "entity_id" not in payload:
                # Try simple lookup
                eid = self.entities.get(name.lower())
                if eid:
                    payload["entity_id"] = eid
                else:
                    # Fallback: if name looks like an entity_id
                    if "." in name:
                        payload["entity_id"] = name
                    else:
                        logger.warning(f"Could not resolve entity name: {name}")

        logger.info(f"Calling Service: {domain}/{service} with {payload}")

        async with ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 200:
                        logger.info(f"Success! {await resp.text()}")
                        return "Success"
                    else:
                        err_text = await resp.text()
                        logger.error(f"Service Call Failed {resp.status}: {err_text}")
                        return f"Failed: {err_text}"
            except Exception as e:
                return f"Error: {str(e)}"

# --- Tool Handler ---
class ToolHandler:
    def __init__(self, ha_client: HomeAssistantClient):
        self.ha = ha_client

    async def handle_tool_call(self, tool_name, args):
        """Dispatches tool calls to specific handlers."""
        logger.info(f"Executing Tool: {tool_name} with args: {args}")
        
        # Ensure name cache is populated at least once
        if not self.ha.entities:
            await self.ha.get_states()

        try:
            if tool_name == "HassSetState":
                return await self._handle_set_state(args)
            elif tool_name == "HassMediaControl":
                return await self._handle_media_control(args)
            elif tool_name == "HassControlVolume":
                return await self._handle_volume(args)
            elif tool_name == "HassSetMute":
                mute = args.get("mute")
                svc = "volume_mute"
                return await self.ha.call_service("media_player", svc, {"is_volume_muted": mute, "name": args.get("name")})
            elif tool_name == "HassLightSet":
                return await self.ha.call_service("light", "turn_on", args)
            elif tool_name == "HassFanSetSpeed":
                return await self.ha.call_service("fan", "set_percentage", args)
            elif tool_name == "HassManageTodoList":
                action = args.get("action")
                svc = "add_item" if action == "add" else "update_item"
                data = {"item": args.get("item")}
                # Todo services often need entity_id of the list. 
                # Use name as entity_id or resolve it.
                if "name" in args:
                    data["name"] = args["name"]
                if action == "complete":
                    data["status"] = "completed"
                return await self.ha.call_service("todo", svc, data)
            elif tool_name == "GetLiveContext":
                return await self._handle_get_context(args)
            elif tool_name == "GetDateTime":
                return datetime.datetime.now().isoformat()
            elif tool_name == "HassBroadcast":
                return await self.ha.call_service("tts", "google_translate_say", {"message": args.get("message"), "entity_id": "media_player.all_speakers"}) # Example default
            else:
                return f"Error: Tool {tool_name} not implemented."
        except Exception as e:
            logger.error(f"Tool Execution Error: {e}")
            return f"Error executing {tool_name}: {e}"

    async def _handle_set_state(self, args):
        state = args.get("state")
        domain = args.get("device_class")
        service = "turn_on"

        del args["state"]
        del args["device_class"]

        payload = {}

        if "entity_id" in args:
            payload["entity_id"] = args["entity_id"]
        elif "name" in args:
            payload["name"] = args["name"]
        else:
            raise "'name' or 'entity_id' required"

        
        if state == "off":
            service = "turn_off"
        elif state == "lock":
            domain = "lock"; service = "lock"
        elif state == "unlock":
            domain = "lock"; service = "unlock"
        elif state == "open":
            domain = "cover"; service = "open_cover"
        elif state == "close":
            domain = "cover"; service = "close_cover"
            
        return await self.ha.call_service(domain, service, payload)

    async def _handle_media_control(self, args):
        cmd = args.get("command")
        svc_map = {
            "play": "media_play",
            "pause": "media_pause",
            "next": "media_next_track",
            "previous": "media_previous_track",
            "stop": "media_stop"
        }
        service = svc_map.get(cmd, "media_play")
        return await self.ha.call_service("media_player", service, args)

    async def _handle_volume(self, args):
        mode = args.get("mode")
        level = args.get("level")
        if mode == "set":
            return await self.ha.call_service("media_player", "volume_set", {"volume_level": level/100.0, "name": args.get("name")})
        elif mode == "increase":
            return await self.ha.call_service("media_player", "volume_up", {"name": args.get("name")})
        elif mode == "decrease":
            return await self.ha.call_service("media_player", "volume_down", {"name": args.get("name")})

    async def _handle_get_context(self, args):
        states = await self.ha.get_states()

        payload = args or {}

        if "name" in payload:
            name = payload.pop("name")
            if "entity_id" not in payload:
                # Try simple lookup
                eid = self.ha.entities.get(name.lower())
                if eid:
                    payload["entity_id"] = eid
                else:
                    # Fallback: if name looks like an entity_id
                    if "." in name:
                        payload["entity_id"] = name
                    else:
                        logger.warning(f"Could not resolve entity name: {name}")

        if "entity_id" in payload:
            return await self.ha.get_state(payload["entity_id"])

        summary = []
        for s in states:
            # Filter huge lists, maybe only include domains from context?
            # For now, simplistic filtering:
            # if s['domain'] in ['light', 'switch', 'media_player', 'sensor', 'weather', 'fan', 'lock', 'cover', 'climate']:
            summary.append(f"{s['entity_id']}: {s['state']}")
        return "\n".join(summary[:100]) # Limit to 100 to avoid token limits

async def fetch_tools_via_http():
    """Fetch tools from the custom component HTTP endpoint."""
    url = f"{HA_URL}/gemini_live/tools" # This matches the view URL defined above (note: HA_URL usually ends in /api)
    
    # NOTE: HA_URL in your tools.py is "http://supervisor/core/api"
    # The view registers at "/api/gemini_live/tools" relative to root.
    # So the full URL is likely "http://supervisor/core/api/gemini_live/tools"
    # We need to construct it carefully.
    
    # Correct URL construction for Supervisor API usage:
    # full_url = "http://supervisor/core/api/gemini_live/tools"

    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        logger.info(f"Loaded {len(data['tools'])} tools from Home Assistant HTTP API")
                        return data["tools"]
                    else:
                        logger.error(f"API Error: {data.get('error')}")
                else:
                    logger.error(f"Failed to fetch tools: {resp.status} {await resp.text()}")
    except Exception as e:
        logger.error(f"HTTP Request failed: {e}")

    return [] # Return empty list on failure

async def fetch_entities_via_http(assistant=None):
    """Fetch entities from the custom component HTTP endpoint."""
    url = f"{HA_URL}/gemini_live/entities" # This matches the view URL defined above (note: HA_URL usually ends in /api)
    
    # NOTE: HA_URL in your entities.py is "http://supervisor/core/api"
    # The view registers at "/api/gemini_live/entities" relative to root.
    # So the full URL is likely "http://supervisor/core/api/gemini_live/entities"
    # We need to construct it carefully.
    
    # Correct URL construction for Supervisor API usage:
    # full_url = "http://supervisor/core/api/gemini_live/entities"

    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        # "Content-Type": "application/json",
        "Content-Type": "text/plain",
    }

    try:
        async with ClientSession() as session:
            async with session.post(url, headers=headers, data=assistant) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        logger.info(f"Loaded {len(data['entities'])} entities from Home Assistant HTTP API")
                        # return data
                        # return data["entities"]
                        return generate_device_context(data)
                    else:
                        logger.error(f"API Error: {data.get('error')}")
                else:
                    logger.error(f"Failed to fetch entities: {resp.status} {await resp.text()}")
    except Exception as e:
        logger.error(f"HTTP Request failed: {e}")

    return [] # Return empty list on failure

def get_tools():
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="HassSetState",
                    description="Changes the state of a device. Use this to turn things on/off, lock/unlock locks, or open/close covers.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "state": {
                                "type": "STRING",
                                "enum": ["on", "off", "lock", "unlock", "open", "close"],
                                "description": "The desired state. Use 'on' for activating, 'lock' for locks, 'open' for covers."
                            },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" },
                            "domain": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            },
                            "device_class": {
                                "type": "STRING",
                                "enum": ["tv", "speaker", "switch", "light", "fan", "lock", "cover"]
                            }
                        },
                        "required": ["state", "device_class"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassMediaControl",
                    description="Controls media playback (pause, resume, skip).",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "command": {
                                "type": "STRING",
                                "enum": ["play", "pause", "next", "previous", "stop"],
                                "description": "The playback command to issue."
                            },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" },
                            "domain": {
                                "type": "ARRAY",
                                "items": { "type": "STRING", "enum": ["media_player"] }
                            }
                        },
                        "required": ["command"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassControlVolume",
                    description="Sets or adjusts the volume of a media player.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "mode": {
                                "type": "STRING",
                                "enum": ["set", "increase", "decrease"],
                                "description": "Use 'set' for a specific percentage, 'increase'/'decrease' for relative adjustments."
                            },
                            "level": {
                                "type": "INTEGER",
                                "description": "The target volume percentage (0-100) or the step amount to change by."
                            },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" },
                            "domain": {
                                "type": "ARRAY",
                                "items": { "type": "STRING", "enum": ["media_player"] }
                            }
                        },
                        "required": ["mode", "level"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassSetMute",
                    description="Mutes or unmutes a media player.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "mute": {
                                "type": "BOOLEAN",
                                "description": "True to mute, False to unmute."
                            },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" },
                            "domain": {
                                "type": "ARRAY",
                                "items": { "type": "STRING", "enum": ["media_player"] }
                            }
                        },
                        "required": ["mute"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassManageTodoList",
                    description="Adds or completes items on a todo list.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "action": {
                                "type": "STRING",
                                "enum": ["add", "complete"],
                                "description": "Whether to add a new item or mark one as finished."
                            },
                            "item": {
                                "type": "STRING",
                                "description": "The text of the item (e.g., 'milk', 'call mom')."
                            },
                            "name": {
                                "type": "STRING",
                                "description": "The name of the list (e.g., 'Shopping List')."
                            }
                        },
                        "required": ["action", "item", "name"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassLightSet",
                    description="Sets the brightness or color of a light.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "brightness": { "type": "INTEGER", "description": "0 to 100" },
                            "color": { "type": "STRING", "description": "Color name or RGB value" },
                            "temperature": { "type": "INTEGER", "description": "Kelvin value" },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" }
                        }
                    }
                ),
                types.FunctionDeclaration(
                    name="HassFanSetSpeed",
                    description="Sets a fan's speed percentage.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "percentage": { "type": "INTEGER" },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" }
                        },
                        "required": ["percentage"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassMediaSearchAndPlay",
                    description="Searches for media and plays it.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "search_query": { "type": "STRING" },
                            "media_class": {
                                "type": "STRING",
                                "enum": ["music", "tv_show", "movie", "podcast", "video"]
                            },
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" }
                        },
                        "required": ["search_query"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassBroadcast",
                    description="Broadcast a message via TTS.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "message": { "type": "STRING" }
                        },
                        "required": ["message"]
                    }
                ),
                types.FunctionDeclaration(
                    name="todo_get_items",
                    description="Get items from a todo list.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "todo_list": { "type": "STRING" },
                            "status": { "type": "STRING", "enum": ["needs_action", "completed"] }
                        },
                        "required": ["todo_list"]
                    }
                ),
                types.FunctionDeclaration(
                    name="HassCancelAllTimers",
                    description="Cancels all active timers in an area.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "area": { "type": "STRING" }
                        }
                    }
                ),
                types.FunctionDeclaration(
                    name="GetDateTime",
                    description="Returns current date and time."
                ),
                types.FunctionDeclaration(
                    name="GetLiveContext",
                    description="Get real-time states (on/off, temp, etc) for answering status questions.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "name": { "type": "STRING" },
                            "area": { "type": "STRING" },
                            "domain": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            },
                            "device_class": {
                                "type": "STRING",
                                "enum": ["tv", "speaker", "switch", "light", "fan", "lock", "cover"]
                            }
                        }
                    }
                )
            ]
        )
    ]