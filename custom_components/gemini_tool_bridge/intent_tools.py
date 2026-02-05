from google.genai import types


def get_intent_tools() -> types.ToolListUnion:
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
                    description="Sets or adjusts the volume of a media player. For mode 'set': [NONE, name]. For mode 'increase'/'decrease': [NONE, area, name].",
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
