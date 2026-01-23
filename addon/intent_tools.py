from google.genai import types
import logging
import datetime
from aiohttp import ClientSession
import os

from device_context import get_name_for_entity

# Reuse logger and constants from tools.py
logger = logging.getLogger(__name__)
HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.getenv("SUPERVISOR_TOKEN")


class HomeAssistantClient:
    """Client for interacting with Home Assistant via Supervisor API."""

    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {HA_TOKEN}",
            "Content-Type": "application/json",
        }
        self.entities = {}  # Cache for name resolution

    async def get_states(self):
        """Fetch all states from Home Assistant."""
        if not HA_TOKEN:
            logger.error("SUPERVISOR_TOKEN not found. Cannot fetch HA states.")
            return []

        async with ClientSession() as session:
            try:
                async with session.get(
                    f"{HA_URL}/states", headers=self.headers
                ) as resp:
                    if resp.status == 200:
                        states = await resp.json()
                        # Update name cache
                        for state in states:
                            if "friendly_name" in state.get("attributes", {}):
                                self.entities[
                                    state["attributes"]["friendly_name"].lower()
                                ] = state["entity_id"]
                        return states
                    else:
                        logger.error(
                            f"Failed to fetch states: [{resp.status}] {await resp.text()}"
                        )
                        return []
            except Exception as e:
                logger.error(f"HA API Error: {e}")
                return []

    async def get_state(self, entity_id):
        """Fetch specific state."""
        async with ClientSession() as session:
            try:
                async with session.get(
                    f"{HA_URL}/states/{entity_id}", headers=self.headers
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
            except Exception as e:
                logger.error(f"HA API Error: {e}")
                return None

    async def fire_intent(self, intent_name, data=None):
        """
        Fires an intent directly to Home Assistant.
        Endpoint: /intent/handle (Standard HA API)
        """
        if not HA_TOKEN:
            return "Error: No API Token"

        url = f"{HA_URL}/intent/handle"
        payload = {"name": intent_name, "data": data or {}}

        logger.info(f"Firing Intent: {intent_name} with {payload['data']}")

        async with ClientSession() as session:
            try:
                async with session.post(
                    url, headers=self.headers, json=payload
                ) as resp:
                    response_json = await resp.json()

                    if resp.status == 200:
                        # Parse the speech response from the intent if available
                        speech = (
                            response_json.get("speech", {})
                            .get("plain", {})
                            .get("speech", "Done.")
                        )
                        logger.info(f"Intent Success: {speech}")
                        return speech
                    else:
                        logger.error(
                            f"Intent Failed {resp.status}: {await resp.text()}"
                        )
                        return f"Failed to execute intent: {await resp.text()}"
            except Exception as e:
                return f"Error firing intent: {str(e)}"


class IntentToolHandler:
    """
    Handles tools defined in intent_tools.py by transforming them
    into Home Assistant Intents defined in intents.yaml.
    """

    def __init__(self, ha_client: HomeAssistantClient):
        self.ha = ha_client

    async def handle_tool_call(self, tool_name, args):
        """Dispatches tool calls to specific intent handlers."""
        logger.info(f"Processing Intent Tool: {tool_name} with args: {args}")

        # Ensure name cache is populated
        if not self.ha.entities:
            await self.ha.get_states()

        # TODO: Only do name resolution for tools that need it
        if not "name" in args and "entity_id" in args:
            args["name"] = get_name_for_entity(args["entity_id"])
            del args["entity_id"]

        try:
            if tool_name == "HassIntentRaw":
                return await self.ha.fire_intent(args.get("name"), args.get("data"))

            elif tool_name == "ProxySetState":
                return await self._handle_proxy_set_state(args)

            elif tool_name == "HassLightSet":
                return await self.ha.fire_intent("HassLightSet", args)

            elif tool_name == "HassFanSetSpeed":
                return await self.ha.fire_intent("HassFanSetSpeed", args)

            elif tool_name == "HassMediaSearchAndPlay":
                return await self.ha.fire_intent("HassMediaSearchAndPlay", args)

            elif tool_name == "ProxyMediaControl":
                return await self._handle_proxy_media_control(args)

            elif tool_name == "ProxyControlVolume":
                return await self._handle_proxy_control_volume(args)

            elif tool_name == "ProxySetMute":
                mute = args.get("mute")
                intent = "HassMediaPlayerMute" if mute else "HassMediaPlayerUnmute"
                # Filter args to valid slots (name, area)
                data = {k: v for k, v in args.items() if k in ["name", "area"]}
                return await self.ha.fire_intent(intent, data)

            elif tool_name == "HassBroadcast":
                return await self.ha.fire_intent("HassBroadcast", args)

            # --- Timer Proxies ---
            elif tool_name == "HassStartTimer":
                return await self.ha.fire_intent("HassStartTimer", args)

            elif tool_name == "HassCancelAllTimers":
                return await self.ha.fire_intent("HassCancelAllTimers", args)

            elif tool_name == "HassCancelTimer":
                return await self.ha.fire_intent("HassCancelTimer", args)

            elif tool_name == "ProxyAdjustTimer":
                operation = args.pop("operation")
                intent = (
                    "HassIncreaseTimer"
                    if operation == "increase"
                    else "HassDecreaseTimer"
                )
                return await self.ha.fire_intent(intent, args)

            elif tool_name == "ProxyPauseResumeTimer":
                action = args.pop("action")
                intent = "HassPauseTimer" if action == "pause" else "HassUnpauseTimer"
                return await self.ha.fire_intent(intent, args)

            # --- Context/Info Tools (Not Intents) ---
            elif tool_name == "GetDateTime":
                return datetime.datetime.now().isoformat()

            elif tool_name == "GetLiveContext":
                return await self._handle_get_context(args)

            else:
                return f"Error: Tool {tool_name} not implemented."

        except Exception as e:
            logger.error(f"Intent Handling Error: {e}")
            return f"Error executing {tool_name}: {e}"

    async def _handle_proxy_set_state(self, args):
        """Maps generic state changes to HassTurnOn/Off intents."""
        state = args.get("state")
        data = {k: v for k, v in args.items() if k != "state"}

        intent_name = "HassTurnOn"  # Default

        # Map generic 'state' to Intent + inferred slots if necessary
        if state == "on":
            intent_name = "HassTurnOn"
        elif state == "off":
            intent_name = "HassTurnOff"
        elif state == "open":
            intent_name = "HassTurnOn"
            # Explicitly helps HA infer it's a cover if no device_class provided
            if "device_class" not in data and "domain" not in data:
                data["domain"] = "cover"
        elif state == "close":
            intent_name = "HassTurnOff"
            if "device_class" not in data and "domain" not in data:
                data["domain"] = "cover"
        elif state == "lock":
            # In HA Intent Land: 'Turning On' a lock usually means engaging it (Locking)
            intent_name = "HassTurnOn"
            if "device_class" not in data:
                data["device_class"] = "lock"
        elif state == "unlock":
            # 'Turning Off' a lock usually means disengaging it (Unlocking)
            intent_name = "HassTurnOff"
            if "device_class" not in data:
                data["device_class"] = "lock"

        return await self.ha.fire_intent(intent_name, data)

    async def _handle_proxy_media_control(self, args):
        """Maps media commands to specific media intents."""
        command = args.get("command")
        data = {k: v for k, v in args.items() if k != "command"}

        if command == "play":
            intent_name = "HassMediaUnpause"  # Resume/Play
        elif command == "pause":
            intent_name = "HassMediaPause"
        elif command == "next":
            intent_name = "HassMediaNext"
        elif command == "previous":
            intent_name = "HassMediaPrevious"
        elif command == "stop":
            # intents.yaml does not have HassMediaStop.
            # HassTurnOff is the standard equivalent for stopping media devices.
            intent_name = "HassTurnOff"
            if "domain" not in data:
                data["domain"] = "media_player"
        else:
            return "Error: Unknown media command"

        return await self.ha.fire_intent(intent_name, data)

    async def _handle_proxy_control_volume(self, args):
        """Maps volume tools to Absolute or Relative volume intents."""
        mode = args.get("mode")
        level = args.get("level")
        data = {k: v for k, v in args.items() if k not in ["mode", "level"]}

        if mode == "set":
            data["volume_level"] = level
            return await self.ha.fire_intent("HassSetVolume", data)
        elif mode in ["increase", "decrease"]:
            # HassSetVolumeRelative takes 'volume_step' (percentage) NOT 'level'
            # Note: The tool uses 'level' for both, but intents.yaml expects 'volume_step'

            # Check if level is provided, otherwise default to a reasonable step
            step = level if level else 10

            if mode == "decrease":
                step = -abs(step)  # Ensure negative
            else:
                step = abs(step)

            data["volume_step"] = step
            return await self.ha.fire_intent("HassSetVolumeRelative", data)

        return "Error: Invalid volume mode"

    async def _handle_get_context(self, args):
        """Helper to get state data for answering questions (Not an intent)."""
        # Logic reused from tools.py to support 'GetLiveContext'
        payload = args or {}

        # Name resolution
        if "name" in payload and "entity_id" not in payload:
            eid = self.ha.entities.get(payload["name"].lower())
            if eid:
                payload["entity_id"] = eid
            elif "." in payload["name"]:
                payload["entity_id"] = payload["name"]

        if "entity_id" in payload:
            return await self.ha.get_state(payload["entity_id"])

        # Fallback: Return summary of all states
        states = await self.ha.get_states()
        summary = []
        for s in states:
            summary.append(f"{s['entity_id']}: {s['state']}")
        logger.info(f"GetLiveContext returning {len(summary)} states")
        return "\n".join(summary)


def get_intent_tools():
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="ProxySetState",
                    description="Changes the state of a device. Use this to turn things on/off, lock/unlock locks, or open/close covers. [name, area, area+name, area+domain, area+device_class, device_class+domain]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "state": {
                                "type": "STRING",
                                "enum": [
                                    "on",
                                    "off",
                                    "lock",
                                    "unlock",
                                    "open",
                                    "close",
                                ],
                                # "description": "The desired state. Use 'on' for activating, 'lock' for locks, 'open' for covers."
                            },
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                            "device_class": {
                                "type": "STRING",
                                "enum": [
                                    "tv",
                                    "speaker",
                                    "switch",
                                    "light",
                                    "fan",
                                    "lock",
                                    "cover",
                                ],
                                "default": "light",
                            },
                        },
                        "required": ["state"],
                    },
                ),
                types.FunctionDeclaration(
                    name="HassLightSet",
                    description="Sets the brightness or color of a light. [name+brightness, name+color, brightness, area+brightness, color, area+color]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "brightness": {
                                "type": "INTEGER",
                                "description": "0 to 100",
                            },
                            "color": {
                                "type": "STRING",
                                "description": "Color name or RGB value",
                            },
                            # "temperature": {
                            #     "type": "INTEGER",
                            #     "description": "Kelvin value",
                            # },
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                        },
                    },
                ),
                types.FunctionDeclaration(
                    name="HassFanSetSpeed",
                    description="Sets a fan's speed percentage. [name, area]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "percentage": {"type": "INTEGER"},
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                        },
                        "required": ["percentage"],
                    },
                ),
                # Media
                types.FunctionDeclaration(
                    name="HassMediaSearchAndPlay",
                    description="Searches for media and plays it. [NONE, area, name, name+area]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "search_query": {"type": "STRING"},
                            "media_class": {
                                "type": "STRING",
                                "enum": [
                                    "music",
                                    "tv_show",
                                    "movie",
                                    "podcast",
                                    "video",
                                ],
                            },
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                        },
                        "required": ["search_query"],
                    },
                ),
                types.FunctionDeclaration(
                    name="ProxyMediaControl",
                    description="Controls media playback (pause, resume, skip). [NONE, area, name]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "command": {
                                "type": "STRING",
                                "enum": ["play", "pause", "next", "previous", "stop"],
                                "description": "The playback command to issue.",
                            },
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                        },
                        "required": ["command"],
                    },
                ),
                types.FunctionDeclaration(
                    name="ProxyControlVolume",
                    description="Sets or adjusts the volume of a media player. [For mode 'set': NONE, name. For mode 'increase'/'decrease': NONE, area, name.]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "mode": {
                                "type": "STRING",
                                "enum": ["set", "increase", "decrease"],
                                "description": "Use 'set' for a specific percentage, 'increase'/'decrease' for relative adjustments.",
                            },
                            "level": {
                                "type": "INTEGER",
                                "description": "The target volume percentage (0-100) or the step amount to change by.",
                            },
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                        },
                        "required": ["mode", "level"],
                    },
                ),
                types.FunctionDeclaration(
                    name="ProxySetMute",
                    description="Mutes or unmutes a media player. [NONE, name]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "mute": {
                                "type": "BOOLEAN",
                                "description": "True to mute, False to unmute.",
                            },
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                        },
                        "required": ["mute"],
                    },
                ),
                types.FunctionDeclaration(
                    name="HassBroadcast",
                    description="Broadcast a message via TTS.",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {"message": {"type": "STRING"}},
                        "required": ["message"],
                    },
                ),
                # Timers
                types.FunctionDeclaration(
                    name="HassStartTimer",
                    description="Starts a timer. [hours, minutes, seconds, hours+minutes, hours+seconds, minutes+seconds, hours+minutes+seconds]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "hours": {
                                "type": "INTEGER",
                                "description": "Number of hours",
                            },
                            "minutes": {
                                "type": "INTEGER",
                                "description": "Number of minutes",
                            },
                            "seconds": {
                                "type": "INTEGER",
                                "description": "Number of seconds",
                            },
                            "name": {
                                "type": "STRING",
                                "description": "Name attached to the timer",
                            },
                            "conversation_command": {
                                "type": "STRING",
                                "description": "Command to execute when timer finishes",
                            },
                        },
                    },
                ),
                types.FunctionDeclaration(
                    name="HassCancelAllTimers",
                    description="Cancels all active timers in an area. [NONE, area]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {"area": {"type": "STRING"}},
                    },
                ),
                types.FunctionDeclaration(
                    name="HassCancelTimer",
                    description="Cancels a timer. [NONE, name, area]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "start_hours": {
                                "type": "INTEGER",
                                "description": "Hours the timer was started with",
                            },
                            "start_minutes": {
                                "type": "INTEGER",
                                "description": "Minutes the timer was started with",
                            },
                            "start_seconds": {
                                "type": "INTEGER",
                                "description": "Seconds the timer was started with",
                            },
                            "name": {
                                "type": "STRING",
                                "description": "Name attached to the timer",
                            },
                            "area": {
                                "type": "STRING",
                                "description": "Area of the device used to start the timer",
                            },
                        },
                    },
                ),
                types.FunctionDeclaration(
                    name="ProxyAdjustTimer",
                    description="Adjusts a timer. [NONE, name, area]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "operation": {
                                "type": "STRING",
                                "enum": ["increase", "decrease"],
                                "description": "Whether to increase or decrease the timer.",
                            },
                            "hours": {
                                "type": "INTEGER",
                                "description": "Number of hours",
                            },
                            "minutes": {
                                "type": "INTEGER",
                                "description": "Number of minutes",
                            },
                            "seconds": {
                                "type": "INTEGER",
                                "description": "Number of seconds",
                            },
                            "start_hours": {
                                "type": "INTEGER",
                                "description": "Hours the timer was started with",
                            },
                            "start_minutes": {
                                "type": "INTEGER",
                                "description": "Minutes the timer was started with",
                            },
                            "start_seconds": {
                                "type": "INTEGER",
                                "description": "Seconds the timer was started with",
                            },
                            "name": {
                                "type": "STRING",
                                "description": "Name attached to the timer",
                            },
                            "area": {
                                "type": "STRING",
                                "description": "Area of the device used to start the timer",
                            },
                        },
                        "required": ["operation"],
                    },
                ),
                types.FunctionDeclaration(
                    name="ProxyPauseResumeTimer",
                    description="Pauses a timer. [NONE, name, area]",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "action": {
                                "type": "STRING",
                                "enum": ["pause", "resume"],
                                "description": "Whether to pause or resume the timer.",
                            },
                            "start_hours": {
                                "type": "INTEGER",
                                "description": "Hours the timer was started with",
                            },
                            "start_minutes": {
                                "type": "INTEGER",
                                "description": "Minutes the timer was started with",
                            },
                            "start_seconds": {
                                "type": "INTEGER",
                                "description": "Seconds the timer was started with",
                            },
                            "name": {
                                "type": "STRING",
                                "description": "Name attached to the timer",
                            },
                            "area": {
                                "type": "STRING",
                                "description": "Area of the device used to start the timer",
                            },
                        },
                        "required": ["action"],
                    },
                ),
                # Helper / Info Tools
                # types.FunctionDeclaration(
                #     name="GetDateTime", description="Returns current date and time."
                # ),
                types.FunctionDeclaration(
                    name="GetLiveContext",
                    description="Get real-time states (on/off, temp, etc) for answering status questions.",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "name": {"type": "STRING"},
                            "entity_id": {"type": "STRING"},
                            "area": {"type": "STRING"},
                            "domain": {"type": "ARRAY", "items": {"type": "STRING"}},
                            "device_class": {
                                "type": "STRING",
                                "enum": [
                                    "tv",
                                    "speaker",
                                    "switch",
                                    "light",
                                    "fan",
                                    "lock",
                                    "cover",
                                ],
                            },
                        },
                    },
                ),
                
                types.FunctionDeclaration(
                    name="HassIntentRaw",
                    description="Sends a raw intent command to Home Assistant.",
                    parameters_json_schema={
                        "type": "OBJECT",
                        "properties": {
                            "name": {
                                "type": "STRING",
                                "description": "The name of the intent to send.",
                                "example": "HassTurnOn",
                            },
                            "data": {
                                "type": "OBJECT",
                                "description": "A key-value map of parameters for the intent.",
                                "example": {"entity_id": "light.living_room"},
                            },
                        },
                        "required": ["name", "data"],
                    },
                ),
            ]
        )
    ]
