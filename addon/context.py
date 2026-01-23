import os
import logging
import traceback
from aiohttp import ClientSession

HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.getenv('SUPERVISOR_TOKEN')

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def get_context(raw=False):
    """
    Fetches entity data (raw) or pre-formatted context string from the Home Assistant component.
    """
    url = f"{HA_URL}/gemini_live/entities"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json" if raw else "text/plain",
    }

    try:
        async with ClientSession() as session:
            async with session.post(url, headers=headers) as resp:
                if resp.status == 200:
                    if raw:
                        data = await resp.json()
                        if data.get("success"):
                            return data
                        else:
                            logger.error(f"API Error fetching raw entities: {data.get('error')}")
                    else:
                        return await resp.text() # Return the pre-formatted string directly
                else:
                    logger.error(f"Failed to fetch context: {resp.status} {await resp.text()}")
    except Exception as e:
        logger.error(f"HTTP Request failed: {e}")
        error_trace = traceback.format_exc()
        logger.error(f"Traceback: {error_trace}")

    return None if raw else "Error: Could not fetch context."
