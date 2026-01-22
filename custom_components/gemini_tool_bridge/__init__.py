"""The Gemini Tool Bridge integration."""

import logging

# import voluptuous as vol
from aiohttp.web import Request, Response

# from voluptuous_openapi import convert
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import http as http_helpers
from homeassistant.helpers import llm
from homeassistant.helpers import device_registry as dr, entity_registry as er

# from homeassistant.helpers import config_validation as cv
from homeassistant.components.google_generative_ai_conversation import conversation
from homeassistant.components.homeassistant import (
    exposed_entities as ha_exposed_entities,
)
import orjson

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Gemini Tool Bridge component."""
    _LOGGER.info("Setting up Gemini Tool Bridge component")

    # Register the Custom HTTP View
    # hass.http.register_view(GeminiToolsView())
    return True


# 2. This is called when you click "Add Integration" in the UI
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Gemini Tool Bridge from a config entry."""

    _LOGGER.info("Setting up Gemini Tool Bridge from config entry")

    # Register the HTTP View (The API endpoint)
    # We check if it's already registered to avoid errors on reload
    tools_view = GeminiToolsView()
    entities_view = GeminiEntitiesView()
    try:
        hass.http.register_view(tools_view)
        hass.http.register_view(entities_view)
    except ValueError:
        pass  # Already registered

    return True


# 3. This is called when you remove the integration
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    return True


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
                user_prompt=None,
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
            user_prompt=None,
            language="en",
        )  # type: ignore

    async def get(self, request: Request):
        """Handle GET requests to fetch tools."""
        hass = request.app["hass"]

        _LOGGER.warning("Received request for Gemini tools")

        try:
            # 1. Get the LLM API for the default 'Assist' pipeline
            # This handles the logic of which entities are 'exposed' to Voice Assistants
            llm_context = self._get_llm_context()
            # Get the LLM API instance (handles entity exposure logic)
            # We assume the default LLM API for Home Assistant
            # llm_apis = llm.async_get_apis(hass)

            exposed_entities = llm._get_exposed_entities(hass, "assist")
            api = llm.AssistAPI(hass)

            llm_api = await api.async_get_api_instance(llm_context)

            # 2. Get the tools (functions) exposed to this API
            tools = llm_api.tools

            _LOGGER.warning(f"Fetched {len(tools)} tools from LLM API")

            # 3. Convert to Gemini's expected JSON Schema
            gemini_tools = []

            for tool in tools:
                # tool_def = {
                #     "name": tool.name,
                #     "description": tool.description,
                #     "parameters": convert(tool.parameters, custom_serializer=llm_api.custom_serializer),
                # }
                tool_def = conversation._format_tool(tool, llm_api.custom_serializer)
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
        assistant = await request.text() or "conversation"

        try:
            ent_reg = er.async_get(hass)
            dev_reg = dr.async_get(hass)

            await ent_reg.async_load()
            await dev_reg.async_load()

            all_states = hass.states.async_all()
            ee = ha_exposed_entities.ExposedEntities(hass)
            await ee._async_load_data()
            # ee._assistants
            # ee.entities
            # exposed_entities = llm._get_exposed_entities(hass, assistant)

            # states = [state for state in all_states if ee.async_should_expose("conversation", state.entity_id)]

            devices = {}
            non_device_entities = []

            for state in all_states:
                if not ee.async_should_expose(assistant, state.entity_id):
                    continue
                entity_entry = ent_reg.async_get(state.entity_id)


                entity_dict = {}
                try:
                  entity_dict = state.as_dict() # Use state.as_dict() to ensure clean base
                except Exception as e:
                    _LOGGER.error(f"Error converting state to dict for {state.entity_id}: {e}")
                    entity_dict = {
                        "entity_id": state.entity_id,
                        "state": state.state,
                        "attributes": state.attributes,
                    }

                if entity_entry:
                    # entity_dict = {
                    #     **entity_entry.extended_dict,
                    #     "name": state.name,
                    #     "friendly_name": state.attributes.get("friendly_name", ""),
                    # }
                    try:
                      entity_dict.update({
                          **entity_entry.extended_dict,
                          "name": state.name,
                          "friendly_name": state.attributes.get("friendly_name", ""),
                      })
                    except Exception as e:
                        _LOGGER.error(f"Error updating entity_dict for {state.entity_id}: {e}")

                if entity_entry and entity_entry.device_id:
                    if entity_entry.device_id not in devices:
                        devices[entity_entry.device_id] = {
                            "device": None,
                            "entities": [],
                        }

                    devices[entity_entry.device_id]["entities"].append(entity_dict)

                    if devices[entity_entry.device_id]["device"] is None:
                        # Look up the device in the Device Registry using the device_id
                        device_entry = dev_reg.async_get(entity_entry.device_id)

                        if device_entry:
                            devices[device_entry.id]["device"] = device_entry.dict_repr
                else:
                    non_device_entities.append(entity_dict)

            # _LOGGER.warning(f"Fetched {len(exposed_devices)} devices from LLM API for assistant '{assistant}'")

            try:
                orjson.dumps(devices)
                _LOGGER.warning("Successfully serialized devices with orjson")
            except Exception as e:
                _LOGGER.error(f"Error serializing devices with orjson: {e}")
            
            try:
                orjson.dumps(non_device_entities)
                _LOGGER.warning("Successfully serialized non-device entities with orjson")
            except Exception as e:
                _LOGGER.error(f"Error serializing non-device entities with orjson: {e}")

            try:
                self.json(devices)
                _LOGGER.warning("Successfully serialized devices with self.json")
            except Exception as e:
                _LOGGER.error(f"Error serializing devices with self.json: {e}")
            
            try:
                self.json(non_device_entities)
                _LOGGER.warning("Successfully serialized non-device entities with self.json")
            except Exception as e:
                _LOGGER.error(f"Error serializing non-device entities with self.json: {e}")

            data = {
                "success": True,
                "devices": devices,
                "non_device_entities": non_device_entities,
            }
            
            # orjson.dumps returns bytes
            json_bytes = orjson.dumps(data)
            return Response(body=json_bytes, content_type="application/json")

            # return self.json(
            #     {
            #         "success": True,
            #         # "entities": exposed_entities,
            #         "devices": devices,
            #         "non_device_entities": non_device_entities,
            #     }
            # )

        except Exception as e:
            _LOGGER.error(f"Error fetching entities: {e}")
            return self.json({"success": False, "error": str(e)})
