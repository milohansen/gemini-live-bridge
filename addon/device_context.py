import os
import re
import logging
import traceback
from aiohttp import ClientSession

HA_URL = "http://supervisor/core/api"
HA_TOKEN = os.getenv('SUPERVISOR_TOKEN')

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


STATIC_DEVICE_CONTEXT_PREFIX = "Smart Home Device Context: An overview of the areas and the devices in this smart home:"
DEVICE_CONTEXT_PREFIX_LINES = [
    "Smart Home Device Context: An overview of the areas and the devices in this smart home:",
    "You are running on My Display, located in the Office area.",
    "",
    "Tool Notes: In the description of each tool, parameters are listed in square brackets [] to indicate possible slot combinations.",
    "For example, [name, area+name] means the tool can be used with either the 'name' parameter alone or the 'area' parameter with the 'name' parameter together, but will fail if area is used alone.",
    "Any tool that can be called with a 'name' parameter can also be called with an 'entity_id' parameter instead of 'name' for more precise targeting.",
    "",
    "Entity Notes: The following lists group entities by their assigned Areas in Home Assistant.",
    "Each entity is represented with its User Friendly Name and Entity ID for tool usage.",
    "Entity names that start with their Area or Device names have been shortened for conciseness. (e.g., 'Living Room Lamp' is shown as 'Lamp' in the Living Room section.)",
]


def generate_device_context(data):
    """
    Generates a context string for an AI assistant from Home Assistant entity data.

    Groups entities by Area to provide spatial context and explicitly maps
    User Friendly Names to Entity IDs for tool usage.
    """

    # Dictionary to group entities by area: { "Area Name": [list of entity strings] }
    area_map = {}

    # Helper to add entries to the map
    def add_to_map(area_name, entry_str):
        name = area_name if area_name else "General / Unassigned"
        # Capitalize and clean up area name (e.g., "living_room" -> "Living Room")
        clean_name = name.replace("_", " ").title()
        if clean_name not in area_map:
            area_map[clean_name] = []
        area_map[clean_name].append(entry_str)

    # 1. Process Devices (These usually have Area IDs)
    if "devices" in data:
        for device_id, device_info in data["devices"].items():
            device_data = device_info.get("device", {})
            entities = device_info.get("entities", [])

            # Get area context
            area = device_data.get("area_id")

            for entity in entities:
                entity_id = entity.get("entity_id")
                attrs = entity.get("attributes", {})

                # Skip backend-only or usually irrelevant entities if needed
                # (e.g., update entities, diagnostic sensors) - keeping generic for now.

                friendly_name = attrs.get(
                    "friendly_name", entity_id.split(".")[1].replace("_", " ")
                ).strip()
                domain = entity_id.split(".")[0]

                if entity_id == "sensor.home_assistant_voice_co2":
                    logger.info(
                        f"friendly_name for {entity_id}: {friendly_name}, area: {area}"
                    )

                if friendly_name.lower().startswith(area.replace("_", " ").lower()):
                    # If the entity name starts with the area name, strip it to be concise.
                    short_name = friendly_name[len(area) :].strip()
                    # Clean up common separators like ": " or "- " using regex
                    short_name = re.sub(r"^[:\-\s]+", "", short_name)

                    logger.info(
                        f"Shortened '{friendly_name}' to '{short_name}' in area '{area}'"
                    )

                    if short_name:
                        friendly_name = short_name

                # Create a concise descriptive line
                # Format: "- Name (Domain: ID)"
                entry = f"- {friendly_name} ({domain}: {entity_id})"
                add_to_map(area, entry)

    # 2. Process Non-Device Entities (Helper groups, Scenes, etc.)
    # These often don't have an area_id in the JSON, so we place them in General
    # unless we infer it (but safer to list as General/Global)
    if "non_device_entities" in data:
        for entity in data["non_device_entities"]:
            entity_id = entity.get("entity_id")
            attrs = entity.get("attributes", {})
            friendly_name = attrs.get("friendly_name", entity_id)
            domain = entity_id.split(".")[0]

            # Note: Non-device entities in this specific JSON schema lack an 'area_id' field.
            # We add them to "General" or "Groups/Helpers"
            entry = f"- {friendly_name} ({domain}: {entity_id})"
            add_to_map("General / Unassigned", entry)

    # 3. Construct the final output string
    lines = ["Smart Home Device Context:", ""]

    # Sort areas alphabetically for consistent output
    sorted_areas = sorted(area_map.keys())

    # Move "General" to the end if it exists
    if "General / Unassigned" in sorted_areas:
        sorted_areas.remove("General / Unassigned")
        sorted_areas.append("General / Unassigned")

    for area in sorted_areas:
        lines.append(f"Area: {area}")
        # Sort entities within area by name
        for item in sorted(area_map[area]):
            lines.append(f"  {item}")
        lines.append("")  # Empty line between areas

    return "\n".join(lines)

entity_name_map = {}

def generate_grouped_device_context(data):
    """
    Generates a device-centric context string.
    Groups all entities belonging to a single device onto one line
    and cleans up redundant naming.
    """
    area_map = {}

    def add_to_map(area_name, entry_str):
        name = area_name if area_name else "General / Unassigned"
        clean_name = name.replace("_", " ").title()
        if clean_name not in area_map:
            area_map[clean_name] = []
        area_map[clean_name].append(entry_str)

    # 1. Process Devices
    if "devices" in data:
        for _, device_info in data["devices"].items():
            device_data = device_info.get("device", {})
            entities = device_info.get("entities", [])

            if not entities:
                continue

            # Prefer user defined name, fallback to system name
            device_name = device_data.get("name_by_user") or device_data.get("name")

            if (
                "Adaptive Lighting" in device_data.get("name", "")
                or "Adaptive Lighting" in device_name
            ):
                continue

            area = device_data.get("area_id")

            # Prepare the list of entities for this device
            entity_strings = []
            for entity in entities:
                eid = entity.get("entity_id")

                label = format_entity_name(entity, device_name, area)

                entity_strings.append(f"{label} ({eid})")

            # Formatting
            if len(entity_strings) == 1:
                # If only one entity, just list it simply
                if entity_strings[0].startswith(device_name):
                    # If the single entity name is same as device name, avoid redundancy
                    entry = f"- {entity_strings[0]}"
                else:
                    entry = f"- {device_name}: {entity_strings[0]}"
            else:
                # Multiple entities: "Device Name: Sensor1 (id), Sensor2 (id)"
                entry = f"- {device_name}: {', '.join(entity_strings)}"

            add_to_map(area, entry)

    # 2. Process Non-Device Entities (Groups, Scenes, Helpers)
    if "non_device_entities" in data:
        for entity in data["non_device_entities"]:
            eid = entity.get("entity_id")
            area = entity.get("area_id")
            label = format_entity_name(entity, None, area)
            if area:
                add_to_map(area, f"- {label} ({eid})")
            else:
              # These usually go to General since they lack area_id in this specific JSON schema
              add_to_map("General / Unassigned", f"- {label} ({eid})")

    # 3. Build Output
    lines = [*DEVICE_CONTEXT_PREFIX_LINES, ""]
    sorted_areas = sorted(area_map.keys())

    # Ensure 'General' is last
    if "General / Unassigned" in sorted_areas:
        sorted_areas.remove("General / Unassigned")
        sorted_areas.append("General / Unassigned")

    for area in sorted_areas:
        lines.append(f"Area: {area}")
        for item in sorted(area_map[area]):
            lines.append(f"  {item}")
        lines.append("")

    return "\n".join(lines)


def format_entity_name(entity, device_name=None, area_name=None):
    """
    Helper to get a cleaned up entity name.
    Strips device and area names from the start if present.
    """
    eid = entity.get("entity_id")

    friendly_name = (
        entity.get("friendly_name")
        or entity.get("name")
        or entity.get("original_name")
        or eid.split(".")[1].replace("_", " ")
    )
    name = friendly_name

    entity_name_map[eid] = name

    # Naming Logic:
    # If the entity name starts with the device name, strip it to be concise.
    # Example: Device="IKEA Monitor", Entity="IKEA Monitor Temperature" -> "Temperature"
    if device_name and name.lower().startswith(device_name.lower()):
        short_name = name[len(device_name) :].strip()
        short_name = re.sub(r"^[:\-\s]+", "", short_name)
        if short_name:
            name = short_name

    # Similarly for area name
    if area_name and name.lower().startswith(area_name.replace("_", " ").lower()):
        short_name = name[len(area_name) :].strip()
        short_name = re.sub(r"^[:\-\s]+", "", short_name)
        if short_name:
            name = short_name

    return name

def get_name_for_entity(entity_id):
    """Retrieve the cleaned up name for a given entity_id."""
    return entity_name_map.get(entity_id)  # Fallback to entity_id if name not found

async def fetch_context_via_http(raw=False):
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
            async with session.post(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        # logger.info(f"Loaded {len(data['entities'])} entities from Home Assistant HTTP API")
                        return data if raw else generate_grouped_device_context(data)
                        # return data["entities"]
                        # return generate_grouped_device_context(data)
                    else:
                        logger.error(f"API Error: {data.get('error')}")
                else:
                    logger.error(f"Failed to fetch entities: {resp.status} {await resp.text()}")
    except Exception as e:
        logger.error(f"HTTP Request failed: {e}")
        error_trace = traceback.format_exc()
        logger.error(f"Traceback: {error_trace}")

    return [] # Return empty list on failure

