"""The Gemini Tool Bridge integration."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

# from homeassistant.helpers import config_validation as cv
# from homeassistant.components.google_generative_ai_conversation import conversation
# from homeassistant.components.homeassistant import (
#     exposed_entities as ha_exposed_entities,
# )

from views import GeminiEntitiesView, GeminiSessionView, GeminiToolsView

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
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
    session_view = GeminiSessionView()
    try:
        hass.http.register_view(tools_view)
        hass.http.register_view(entities_view)
        hass.http.register_view(session_view)
    except ValueError:
        pass  # Already registered

    return True

# 3. This is called when you remove the integration
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    return True
