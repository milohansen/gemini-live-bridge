import os
import google.genai as genai


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY and os.path.exists("/data/options.json"):
    try:
        import json

        with open("/data/options.json", "r") as f:
            options = json.load(f)
            GEMINI_API_KEY = options.get("gemini_api_key")
    except Exception:
        pass

gemini_client = genai.Client(
    http_options={
        "api_version": "v1alpha",
    },
    api_key=GEMINI_API_KEY
)
