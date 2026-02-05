"""Generation of context for the Gemini model."""
import re
from typing import TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.components.homeassistant import (
    exposed_entities as ha_exposed_entities,
)

DEVICE_CONTEXT_PREFIX_LINES = [
    # TODO: Update location details as appropriate for the deployment
    "You are an AI assistant integrated with a Home Assistant smart home system.",
    "You are running on My Display, located in the Office area of an apartment in Jamaica Plain, MA. Use this location for any location-based context like weather or time.",
    "",
    "Tool Notes: In the description of each tool, parameters are listed in square brackets [] to indicate possible slot combinations.",
    "For example, [name, area+name] means the tool can be used with either the 'name' parameter alone or the 'area' parameter with the 'name' parameter together, but will fail if area is used alone.",
    "Any tool that can be called with a 'name' parameter can also be called with an 'entity_id' parameter instead of 'name' for more precise targeting.",
    "",
    "Entity Notes: The following lists group entities by their assigned Areas in Home Assistant.",
    "Each entity is represented with its User Friendly Name and Entity ID for tool usage.",
    "Entity names that start with their Device name have been shortened. A '*' indicates this (e.g., 'Humidifier Temperature' is shown as '* Temperature' under Humidifier.)",
    "The same process applies to entity names that start with their Area name have been shortened for conciseness. A '^' indicates this (e.g., 'Living Room Lamp' is shown as '^ Lamp' in the Living Room section.)",
    "",
    "Smart Home Device Context: An overview of the areas and the devices in this smart home:",
]

entity_name_map: dict[str, str] = {}

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

    if device_name and name.lower().startswith(device_name.lower()):
        short_name = name[len(device_name) :].strip()
        short_name = re.sub(r"^[:\-\s]+", "", short_name)
        if short_name:
            name = "*" + short_name

    if area_name and name.lower().startswith(area_name.replace("_", " ").lower()):
        short_name = name[len(area_name) :].strip()
        short_name = re.sub(r"^[:\-\s]+", "", short_name)
        if short_name:
            name = "^" + short_name

    return name

def format_device_name(device_name: str, area_name=None):
    """
    Helper to get a cleaned up entity name.
    Strips device and area names from the start if present.
    """

    name = device_name

    if area_name and name.lower().startswith(area_name.replace("_", " ").lower()):
        short_name = name[len(area_name) :].strip()
        short_name = re.sub(r"^[:\-\s]+", "", short_name)
        if short_name:
            name = "^" + short_name

    return name


def generate_grouped_device_context(data):
    """
    Generates a device-centric context string.
    """
    area_map = {}

    def add_to_map(area_name, entry_str):
        name = area_name if area_name else "General / Unassigned"
        clean_name = name.replace("_", " ").title()
        if clean_name not in area_map:
            area_map[clean_name] = []
        area_map[clean_name].append(entry_str)

    if "devices" in data:
        for _, device_info in data["devices"].items():
            device_data = device_info.get("device", {})
            entities = device_info.get("entities", [])

            if not entities:
                continue

            device_name = device_data.get("name_by_user") or device_data.get("name")
            if (
                "Adaptive Lighting" in device_data.get("name", "")
                or "Adaptive Lighting" in device_name
            ):
                continue

            area = device_data.get("area_id")
            entity_strings = []
            for entity in entities:
                eid = entity.get("entity_id")
                label = format_entity_name(entity, device_name, area)
                entity_strings.append(f"{label} ({eid})")

            # if len(entity_strings) == 1:
            #     if entity_strings[0].startswith(device_name):
            #         entry = f"- {entity_strings[0]}"
            #     else:
            #         entry = f"- {device_name}: {entity_strings[0]}"
            # else:

            entry = f"- {format_device_name(device_name, area)}: {', '.join(entity_strings)}"

            add_to_map(area, entry)

    if "non_device_entities" in data:
        for entity in data["non_device_entities"]:
            eid = entity.get("entity_id")
            area = entity.get("area_id")
            label = format_entity_name(entity, None, area)
            if area:
                add_to_map(area, f"- {label} ({eid})")
            else:
              add_to_map("General / Unassigned", f"- {label} ({eid})")

    lines = [*DEVICE_CONTEXT_PREFIX_LINES, ""]
    sorted_areas = sorted(area_map.keys())

    if "General / Unassigned" in sorted_areas:
        sorted_areas.remove("General / Unassigned")
        sorted_areas.append("General / Unassigned")

    for area in sorted_areas:
        lines.append(f"Area: {area}")
        for item in sorted(area_map[area]):
            lines.append(f"  {item}")
        lines.append("")

    return "\n".join(lines)


class RawEntities(TypedDict):
    """Class to hold raw entities data."""
    devices: dict[str, dict]
    non_device_entities: list[dict]

async def get_raw_entities(hass: HomeAssistant):
    """
    Fetches and structures entity and device data directly from Home Assistant.
    This logic is extracted from the GeminiEntitiesView.post method.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    all_states = hass.states.async_all()
    ee = ha_exposed_entities.ExposedEntities(hass)
    await ee._async_load_data()

    devices = {}
    non_device_entities = []

    for state in all_states:
        if not ee.async_should_expose("conversation", state.entity_id):
            continue
        entity_entry = ent_reg.async_get(state.entity_id)

        entity_dict = {
            "entity_id": state.entity_id,
            "state": state.state,
            "name": state.name,
            "friendly_name": state.attributes.get("friendly_name"),
        }

        if entity_entry:
            entity_dict = {**entity_entry.extended_dict, **entity_dict}

        if entity_entry and entity_entry.device_id:
            if entity_entry.device_id not in devices:
                devices[entity_entry.device_id] = {
                    "device": None,
                    "entities": [],
                }
            devices[entity_entry.device_id]["entities"].append(entity_dict)
            if devices[entity_entry.device_id]["device"] is None:
                device_entry = dev_reg.async_get(entity_entry.device_id)
                if device_entry:
                    devices[device_entry.id]["device"] = device_entry.dict_repr
        else:
            non_device_entities.append(entity_dict)

    return RawEntities(devices=devices, non_device_entities=non_device_entities)

async def generate_context_from_ha(hass: HomeAssistant):
    """The main function to get the context string directly from HA."""
    raw_data = await get_raw_entities(hass)
    # This call populates the entity_name_map
    context = generate_grouped_device_context(raw_data)
    return context
