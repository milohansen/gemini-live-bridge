"""The Gemini Tool Bridge integration."""
import logging
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import http as http_helpers
from homeassistant.helpers import llm
from homeassistant.helpers import config_validation as cv

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
    
    # Register the HTTP View (The API endpoint)
    # We check if it's already registered to avoid errors on reload
    view = GeminiToolsView()
    try:
        hass.http.register_view(view)
    except ValueError:
        pass # Already registered

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

    async def get(self, request):
        """Handle GET requests to fetch tools."""
        hass = request.app["hass"]
        
        try:
            # 1. Get the LLM API for the default 'Assist' pipeline
            # This handles the logic of which entities are 'exposed' to Voice Assistants
            llm_context = llm.LLMContext("homeassistant", None, None, None, "conversation", "device_id")
            # Get the LLM API instance (handles entity exposure logic)
            # We assume the default LLM API for Home Assistant
            llm_apis = llm.async_get_apis(hass)

            exposed_entities = llm._get_exposed_entities(hass, "homeassistant")
            llm_api = await llm.async_get_api(hass, "homeassistant", llm_context)
            
            # 2. Get the tools (functions) exposed to this API
            tools = llm_api.tools
            
            # 3. Convert to Gemini's expected JSON Schema
            gemini_tools = []
            
            for tool in tools:
                try:
                    schema = tool.parameters.schema
                except Exception:
                    # Fallback for tools that might not implement parameters() strictly
                    schema = {}

                tool_def = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "OBJECT",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", []),
                    }
                }
                gemini_tools.append(tool_def)

            return self.json({"success": True, "tools": gemini_tools})
            
        except Exception as e:
            _LOGGER.error(f"Error fetching tools: {e}")
            return self.json({"success": False, "error": str(e)})
