"""The Gemini Tool Bridge integration."""

import logging
import os
import traceback

from aiohttp.web import Request, Response

from voluptuous_openapi import convert
from homeassistant.core import HomeAssistant
from homeassistant.helpers import http as http_helpers
from homeassistant.helpers import llm

import datetime

# from homeassistant.helpers import config_validation as cv
# from homeassistant.components.google_generative_ai_conversation import conversation
# from homeassistant.components.homeassistant import (
#     exposed_entities as ha_exposed_entities,
# )
from context import (
    generate_context_from_ha,
    generate_grouped_device_context,
    get_raw_entities,
    entity_name_map,
)

from const import DOMAIN
import google.genai as genai

_LOGGER = logging.getLogger(__name__)

# THIS WON'T WORK BUT I DON'T KNOW HOW TO GET IT FROM CONFIG FLOW HERE
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY and os.path.exists("/data/options.json"):
    try:
        import json

        with open("/data/options.json", "r") as f:
            options = json.load(f)
            GEMINI_API_KEY = options.get("gemini_api_key")
    except Exception:
        pass


class GeminiSessionView(http_helpers.HomeAssistantView):
    """A view to create a session for direct connection."""

    url = "/api/gemini_live/session"
    name = "api:gemini_live:session"
    requires_auth = True

    gemini_client = genai.Client(
        http_options={
            "api_version": "v1alpha",
        },
        api_key=GEMINI_API_KEY,
    )

    async def post(self, request: Request):
        """Handle POST requests to create a session."""
        hass: HomeAssistant = request.app["hass"]
        data = await request.json()
        api_key = data.get("api_key")

        if not api_key:
            return self.json(
                {"success": False, "error": "API key is required"}, status_code=400
            )

        _LOGGER.info("Received request for a new Gemini session")

        try:
            # 1. Generate context and tools
            context = await generate_context_from_ha(hass)

            tools_view = GeminiToolsView()
            llm_context = tools_view._get_llm_context()
            api = llm.AssistAPI(hass)
            llm_api = await api.async_get_api_instance(llm_context)
            tools = llm_api.tools

            gemini_tools = []
            for tool in tools:
                tool_def = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": convert(
                        tool.parameters, custom_serializer=llm_api.custom_serializer
                    ),
                }
                gemini_tools.append(tool_def)

            # 2. Create ephemeral token

            now = datetime.datetime.now(tz=datetime.timezone.utc)

            token = self.gemini_client.auth_tokens.create(
                uses=10,
                expire_time=now + datetime.timedelta(hours=20),
                new_session_expire_time=now + datetime.timedelta(hours=1),
                http_options={"api_version": "v1alpha"},
                live_connect_constraints={},
            )

            return self.json(
                {
                    "success": True,
                    "token": token.name,
                    "context": context,
                    "tools": gemini_tools,
                }
            )

        except Exception as e:
            _LOGGER.error(f"Error creating session: {e}")
            error_trace = traceback.format_exc()
            _LOGGER.error(f"Traceback: {error_trace}")
            return self.json({"success": False, "error": str(e)})


class GeminiToolsView(http_helpers.HomeAssistantView):
    """A simple view to expose HA's LLM tools via HTTP."""

    url = "/api/gemini_live/tools"
    name = "api:gemini_live:tools"
    requires_auth = True  # Requires the Supervisor Token or Long-Lived Token

    def _get_llm_context(self):
        """Create LLMContext safely handling different HA versions."""
        # Try the most recent signature (Platform, Context, Prompt, Language, Assistant, DeviceID)
        try:
            return llm.LLMContext(
                platform=DOMAIN,
                context=None,
                language="en",
                assistant="conversation",
                device_id=None,
            )  # type: ignore
        except TypeError:
            pass

        # Fallback to older signature (minus Device ID)
        try:
            return llm.LLMContext(
                platform=DOMAIN,
                context=None,
                user_prompt=None,  # type: ignore
                language="en",
                assistant="conversation",
                device_id=None,
            )
        except TypeError:
            pass

        # Fallback to very old/minimal signature
        return llm.LLMContext(
            platform=DOMAIN,
            context=None,
            user_prompt=None,  # type: ignore
            language="en",
        )  # type: ignore

    async def get(self, request: Request):
        """Handle GET requests to fetch tools."""
        hass = request.app["hass"]

        _LOGGER.info("Received request for Gemini tools")

        try:
            # 1. Get the LLM API for the default 'Assist' pipeline
            # This handles the logic of which entities are 'exposed' to Voice Assistants
            llm_context = self._get_llm_context()
            # Get the LLM API instance (handles entity exposure logic)
            # We assume the default LLM API for Home Assistant
            # llm_apis = llm.async_get_apis(hass)

            # exposed_entities = llm._get_exposed_entities(hass, "assist")
            api = llm.AssistAPI(hass)

            llm_api = await api.async_get_api_instance(llm_context)

            # 2. Get the tools (functions) exposed to this API
            tools = llm_api.tools

            _LOGGER.info(f"Fetched {len(tools)} tools from LLM API")

            # 3. Convert to Gemini's expected JSON Schema
            gemini_tools = []

            for tool in tools:
                tool_def = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": convert(
                        tool.parameters, custom_serializer=llm_api.custom_serializer
                    ),
                }
                # tool_def = conversation._format_tool(tool, llm_api.custom_serializer)
                gemini_tools.append(tool_def)

            return self.json({"success": True, "tools": gemini_tools})

        except Exception as e:
            _LOGGER.error(f"Error fetching tools: {e}")
            return self.json({"success": False, "error": str(e)})


class GeminiEntitiesView(http_helpers.HomeAssistantView):
    """A simple view to expose HA's LLM tools via HTTP."""

    url = "/api/gemini_live/entities"
    name = "api:gemini_live:entities"
    requires_auth = True  # Requires the Supervisor Token or Long-Lived Token

    async def get(self, request: Request):
        """Handle GET requests to fetch entities."""
        hass = request.app["hass"]

        _LOGGER.info("Received GET request for Gemini entities")

        try:
            exposed_entities = llm._get_exposed_entities(hass, "assist")

            # _LOGGER.warning(f"Fetched {len(exposed_entities)} entities from LLM API")

            return self.json({"success": True, "entities": exposed_entities})

        except Exception as e:
            _LOGGER.error(f"Error fetching entities: {e}")
            return self.json({"success": False, "error": str(e)})

    async def post(self, request: Request):
        """Handle POST requests to fetch entities."""
        hass: HomeAssistant = request.app["hass"]
        _LOGGER.info("Received POST request for Gemini entities")

        try:
            raw_entities = await get_raw_entities(hass)

            # Check content type to decide on response format
            if request.content_type == "application/json":
                # For the web UI, include the name map
                return self.json(
                    {
                        "success": True,
                        **raw_entities,
                        "entity_name_map": entity_name_map,
                    }
                )
            else:
                # For the addon, generate the formatted context string
                formatted_context = generate_grouped_device_context(raw_entities)
                return Response(text=formatted_context, content_type="text/plain")

        except Exception as e:
            _LOGGER.error(f"Error fetching entities: {e}")
            error_trace = traceback.format_exc()
            _LOGGER.error(f"Traceback: {error_trace}")
            return self.json({"success": False, "error": str(e)})
