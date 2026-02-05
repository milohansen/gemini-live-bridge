"""The Gemini Tool Bridge integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .gemini import generate_config, generate_token, get_gemini_client
from .views import (
    GeminiConfigView,
    GeminiEntitiesView,
    GeminiSessionView,
    GeminiToolsView,
    CancelTimerView,
    cancel_timer,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up the Gemini Tool Bridge component."""
    _LOGGER.info("Setting up Gemini Tool Bridge component")

    # tools_view = GeminiToolsView()
    # entities_view = GeminiEntitiesView()
    # try:
    #     hass.http.register_view(tools_view)
    #     hass.http.register_view(entities_view)
    # except ValueError:
    #     pass  # Already registered
    return True


# 2. This is called when you click "Add Integration" in the UI
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Gemini Tool Bridge from a config entry."""

    _LOGGER.info("Setting up Gemini Tool Bridge from config entry")

    # Register the HTTP View (The API endpoint)
    # We check if it's already registered to avoid errors on reload
    tools_view = GeminiToolsView()
    entities_view = GeminiEntitiesView()
    config_view = GeminiConfigView()
    session_view = GeminiSessionView(entry.data["api_key"])
    cancel_timer_view = CancelTimerView()
    try:
        hass.http.register_view(tools_view)
        hass.http.register_view(entities_view)
        hass.http.register_view(config_view)
        hass.http.register_view(session_view)
        hass.http.register_view(cancel_timer_view)
    except ValueError:
        pass  # Already registered

    async def get_token_action(call: ServiceCall) -> ServiceResponse:
        """Handle the service action call."""
        token = await generate_token(get_gemini_client(entry.data["api_key"]), hass)
        return {"token": token.name}

    hass.services.async_register(
        DOMAIN, "get_token", get_token_action, supports_response=SupportsResponse.ONLY
    )

    async def get_config_action(call: ServiceCall) -> ServiceResponse:
        """Handle the service action call."""
        config = await generate_config(hass)
        return {"config": config.model_dump()}

    hass.services.async_register(
        DOMAIN, "get_config", get_config_action, supports_response=SupportsResponse.ONLY
    )

    async def cancel_timer_action(call: ServiceCall) -> ServiceResponse:
        """Handle the service action call."""
        try:
            cancel_timer(hass, call.data["timer_id"])
        except Exception as e:
            _LOGGER.error(f"Error cancelling timer: {e}")

    hass.services.async_register(DOMAIN, "cancel_timer", cancel_timer_action)

    return True


# 3. This is called when you remove the integration
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    return True
