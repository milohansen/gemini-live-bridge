"""The Gemini Tool Bridge integration."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components import websocket_api
from homeassistant.helpers import llm
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Gemini Tool Bridge component."""
    
    # Register a custom WebSocket command that your Add-on will call
    websocket_api.async_register_command(
        hass, 
        "gemini_live/get_tools", 
        websocket_get_tools, 
        schema=vol.Schema({})
    )
    return True

@websocket_api.websocket_command({
    vol.Required("type"): "gemini_live/get_tools",
})
@websocket_api.async_response
async def websocket_get_tools(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Generate and return the tool definitions for Gemini."""
    
    # 1. Get the 'API' that manages exposed entities. 
    # We use the default assistant ID (conversation.default) or a specific one.
    # This automatically respects the "Expose" settings in HA UI.
    try:
        # Get the LLM API instance (handles entity exposure logic)
        # We assume the default LLM API for Home Assistant
        llm_api = await llm.async_get_api(hass, "homeassistant", llm.LLM_API_ASSIST)
        
        # 2. Get the tools (functions) exposed to this API
        # This returns a list of Tool objects (TurnLightOn, GetWeather, etc.)
        tools = llm_api.tools
        
        # 3. Convert to Gemini's expected JSON Schema
        # Gemini expects: { "function_declarations": [ ... ] }
        gemini_tools = []
        
        for tool in tools:
            # Helper to convert HA's internal schema to OpenAI/Gemini format
            # Note: HA's format is very similar to OpenAI's.
            # We might need to map it slightly depending on exact Gemini reqs.
            schema = tool.parameters()
            
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

        connection.send_result(msg["id"], {"tools": gemini_tools})
        
    except Exception as e:
        connection.send_error(msg["id"], "tool_error", str(e))