import re
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


STATIC_DEVICE_CONTEXT_PREFIX = (
    "Smart Home Device Context: An overview of the areas and the devices in this smart home:"
)
DEVICE_CONTEXT_PREFIX_LINES = [
    "Smart Home Device Context: An overview of the areas and the devices in this smart home:",
    "",
    "Note: The following lists group entities by their assigned Areas in Home Assistant.",
    "Each entity is represented with its User Friendly Name and Entity ID for clarity.",
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
                    logger.info(f"friendly_name for {entity_id}: {friendly_name}, area: {area}")

                if friendly_name.lower().startswith(area.replace("_", " ").lower()):
                    # If the entity name starts with the area name, strip it to be concise.
                    short_name = friendly_name[len(area) :].strip()
                    # Clean up common separators like ": " or "- " using regex
                    short_name = re.sub(r"^[:\-\s]+", "", short_name)

                    logger.info(f"Shortened '{friendly_name}' to '{short_name}' in area '{area}'")

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
                friendly_name = entity.get("attributes", {}).get("friendly_name") or eid

                # Naming Logic:
                # If the entity name starts with the device name, strip it to be concise.
                # Example: Device="IKEA Monitor", Entity="IKEA Monitor Temperature" -> "Temperature"
                label = friendly_name
                if device_name and friendly_name.lower().startswith(
                    device_name.lower()
                ):
                    # Remove the device name from the start
                    short_name = friendly_name[len(device_name) :].strip()
                    # Clean up common separators like ": " or "- " using regex
                    short_name = re.sub(r"^[:\-\s]+", "", short_name)

                    if short_name:
                        label = short_name
                
                # Additional check to remove area name redundancy
                # E.g., Area="Living Room", Entity="Living Room Lamp" -> "Lamp"
                if area and label.lower().startswith(area.replace("_", " ").lower()):
                    # If the entity name starts with the area name, strip it to be concise.
                    short_name = label[len(area) :].strip()
                    # Clean up common separators like ": " or "- " using regex
                    short_name = re.sub(r"^[:\-\s]+", "", short_name)

                    if short_name:
                        label = short_name

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
            friendly_name = entity.get("attributes", {}).get("friendly_name") or eid
            # These usually go to General since they lack area_id in this specific JSON schema
            add_to_map("General / Unassigned", f"- {friendly_name} ({eid})")

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


STATIC_DEVICE_CONTEXT = """
Static Context: An overview of the areas and the devices in this smart home:
- names: 'TV'
  domain: media_player
  areas: Living Room
- names: Bedroom CO2
  domain: sensor
  areas: Bedroom
- names: Bedroom Humidity
  domain: sensor
  areas: Bedroom
- names: Bedroom Temperature
  domain: sensor
  areas: Bedroom
- names: Forecast Home
  domain: weather
- names: Google Gang
  domain: media_player
- names: Home Assistant Voice
  domain: media_player
  areas: Bedroom
- names: Home group
  domain: media_player
- names: Humidifier Fan
  domain: fan
  areas: Bedroom
- names: Humidifier Humidity, Temperature
  domain: sensor
  areas: Bedroom
- names: IKEA Air Quality Monitor (CO2, Humidity, PM2.5, Temp)
  domain: sensor
  areas: Living Room
- names: Kitchen Display, Speaker
  domain: media_player
  areas: Kitchen
- names: Living Room Lamp
  domain: light
  areas: Living Room
- names: Living Room Speaker, TV
  domain: media_player
  areas: Living Room
- names: Marcelle's Bedside Lamp
  domain: light
  areas: Bedroom
- names: Marcelle's Desk Light
  domain: light
  areas: Office
- names: Milo's Bedside Lamp
  domain: light
  areas: Bedroom
- names: Milo's Desk Light
  domain: light
  areas: Office
- names: My Display Screen
  domain: light
  areas: Kitchen
- names: MyCO2 FA0B (CO2, Humidity, Temp)
  domain: sensor
  areas: Office
- names: Pole Lamp
  domain: light
  areas: Dining Room
- names: Shopping List
  domain: todo
- names: Squire
  domain: light
  areas: Dining Room
- names: TV Lights
  domain: light
  areas: Living Room
- names: Tea, Tea Too
  domain: timer
- names: WiZ A21.E26
  domain: light
"""
