import yaml
import requests
import json

# Configuration
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
}


def fetch_yaml(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return yaml.safe_load(response.text)
    except Exception as e:
        print(f"Error fetching YAML: {e}")
        return None


def generate_gemini_schema(intents_data):
    tools = []

    if not isinstance(intents_data, dict):
        print("Error: Root of YAML is not a dictionary.")
        return []

    for intent_name, intent_data in intents_data.items():
        if not isinstance(intent_data, dict):
            continue

        # 1. Basic Info
        description = intent_data.get(
            "description", f"Execute the {intent_name} command."
        )

        # 2. Build Properties (All possible slots)
        slots_source = intent_data.get("slots", {})
        properties = {}

        def process_slot(slot_name, slot_desc=None):
            param_type = SLOT_TYPE_MAPPING.get(slot_name, "STRING")
            if not slot_desc:
                slot_desc = f"The {slot_name}."

            properties[slot_name] = {"type": param_type, "description": slot_desc}

        # Handle Dict-style vs List-style slots
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

        # 3. Build 'anyOf' from slot_combinations
        # slot_combinations is typically a list of dicts: [{'name': 'name', 'area': 'area'}, ...]
        # We need to extract the KEYS from those dicts to form the required lists.
        slot_combinations = intent_data.get("slot_combinations", [])
        any_of_list = []

        if slot_combinations:
            # print(
            #     f"Processing slot_combinations for intent '{intent_name}': {slot_combinations}"
            # )
            for name, combo in slot_combinations.items():
                if isinstance(combo, dict):
                    slots = combo.get("slots", [])

                    if len(slots) == 0:
                        continue

                    any_of_list.append(
                        {
                            "required": slots,
                            "description": combo.get("description"),
                            "example": combo.get("example"),
                        }
                    )

        print(
            f"Processed slot_combinations for intent '{intent_name}': {len(any_of_list)} combinations found."
        )
        # 4. Construct Final Tool Object
        parameters_object = {
            "type": "OBJECT",
            "properties": properties,
        }

        # If we found combinations, use 'anyOf' strict validation
        if any_of_list:
            if len(any_of_list) == 1:
                # If only one combination, no need for anyOf
                parameters_object.update(any_of_list[0])
            else:
                parameters_object["anyOf"] = any_of_list
        else:
            # Fallback: if no combinations defined, maybe default to optional or allow all?
            # Usually we leave required empty to make slots optional, or set them if known.
            parameters_object["required"] = []

        tool = {
            "name": intent_name,
            "description": description,
            "parameters": parameters_object,
        }
        tools.append(tool)

    return tools


def main():
    print(f"Fetching intents from: {INTENTS_URL}...")
    yaml_data = fetch_yaml(INTENTS_URL)

    if yaml_data:
        print("Generating Gemini schema with 'anyOf' support...")
        gemini_tools = generate_gemini_schema(yaml_data)

        # Output result
        with open("addon/scratch/gemini_tools_declarations_v2.json", "w") as f:
            json.dump(gemini_tools, f, indent=2)

        print(f"\nSuccessfully generated {len(gemini_tools)} tool declarations.")


if __name__ == "__main__":
    main()
