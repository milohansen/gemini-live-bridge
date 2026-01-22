import yaml
import requests
import json

INTENTS_URL = (
    "https://raw.githubusercontent.com/OHF-Voice/intents/refs/heads/main/intents.yaml"
)

SLOT_TYPE_MAPPING = {
    "brightness": "INTEGER",
    "percentage": "INTEGER",
    "position": "INTEGER",
    "temperature": "NUMBER",
    "duration": "INTEGER",
    "count": "INTEGER",
    "volume_level": "INTEGER",
}

# Parameters that are logically required for the action to make sense at all
# (e.g., you can't set a position without a number)
ALWAYS_REQUIRED = {
    "HassSetPosition": ["position"],
    "HassClimateSetTemperature": ["temperature"],
    "HassSetVolume": ["volume_level"],
    "HassBroadcast": ["message"],
    "HassShoppingListAddItem": ["item"],
    "HassListAddItem": ["item", "name"],
}


def fetch_yaml(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return yaml.safe_load(response.text)
    except Exception as e:
        print(f"Error fetching YAML: {e}")
        return None


def generate_optimized_schema(intents_data):
    tools = []

    if not isinstance(intents_data, dict):
        return []

    for intent_name, intent_data in intents_data.items():
        if not isinstance(intent_data, dict):
            continue

        # 1. Concise Description
        # We strip specific combination logic from the description.
        description = intent_data.get("description", f"Execute {intent_name}")

        # 2. Build Flat Properties
        slots_source = intent_data.get("slots", {})
        properties = {}

        def process_slot(slot_name, slot_desc=None):
            param_type = SLOT_TYPE_MAPPING.get(slot_name, "STRING")
            if not slot_desc:
                slot_desc = f"Target {slot_name}"

            properties[slot_name] = {"type": param_type, "description": slot_desc}

        if isinstance(slots_source, dict):
            for slot, details in slots_source.items():
                desc = details.get("description") if isinstance(details, dict) else None
                process_slot(slot, desc)
        elif isinstance(slots_source, list):
            for slot in slots_source:
                if isinstance(slot, dict):
                    process_slot(slot.get("name"), slot.get("description"))
                elif isinstance(slot, str):
                    process_slot(slot)

        # 3. Determine 'Required' fields
        # Instead of strict combinations, we only require fields that are
        # absolutely critical for the function to exist (defined in ALWAYS_REQUIRED)
        required_fields = ALWAYS_REQUIRED.get(intent_name, [])
        # Filter to ensure the required field actually exists in properties
        required_fields = [f for f in required_fields if f in properties]

        tool = {
            "name": intent_name,
            "description": description,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
                "required": required_fields,
            },
        }
        tools.append(tool)

    return tools


def main():
    print(f"Fetching intents from: {INTENTS_URL}...")
    yaml_data = fetch_yaml(INTENTS_URL)

    if yaml_data:
        print("Generating optimized flat schema...")
        gemini_tools = generate_optimized_schema(yaml_data)

        # Output result
        with open("addon/scratch/gemini_tools_declarations_v3.json", "w") as f:
            json.dump(gemini_tools, f, indent=2)
        print(f"\nGenerated {len(gemini_tools)} tools.")


if __name__ == "__main__":
    main()
