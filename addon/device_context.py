STATIC_DEVICE_CONTEXT_PREFIX = "Static Context: An overview of the areas and the devices in this smart home:"

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
                
                friendly_name = attrs.get("friendly_name", entity_id.split(".")[1].replace("_", " "))
                domain = entity_id.split(".")[0]
                
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
        lines.append("") # Empty line between areas

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


