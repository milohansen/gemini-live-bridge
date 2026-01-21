# Gemini Live Bridge for Home Assistant

A high-performance voice assistant bridge that connects **ESPHome** audio satellites directly to **Google Gemini Live**.

This project bypasses the standard Home Assistant STT → LLM → TTS pipeline to achieve low-latency, natural conversations. It uses a **Home Assistant Add-on** to handle the heavy audio processing and a **Custom Component** to expose your Home Assistant entities as "tools" to Gemini.

## 🚀 Architecture

The system consists of three parts:

1.  **ESPHome Device (Satellite):** Streams raw audio (UDP) to the Add-on and plays back received audio.
2.  **Gemini Live Proxy (Add-on):**
    * Receives UDP audio from ESP32.
    * Performs VAD (Voice Activity Detection).
    * Manages the WebSocket connection to Google Gemini Live.
    * Handles audio resampling and buffering.
3.  **Gemini Tool Bridge (Integration):**
    * Exposes Home Assistant entities (lights, switches, media players) to the Add-on.
    * Generates the JSON schema required for Gemini's function calling.

## 📋 Prerequisites

* **Hardware:** ESP32-S3 device (recommended) with an I2S Microphone (e.g., INMP441) and I2S Amplifier (e.g., MAX98357A).
* **Software:** Home Assistant OS (required for Add-ons).
* **API Key:** [Google Gemini API Key](https://aistudio.google.com/).

---

## 🛠️ Installation

### Part 1: The Custom Component
This component allows the Add-on to "see" your Home Assistant devices.

1.  **HACS Install (Recommended):**
    * Add this repository to HACS as a **Custom Repository** (Type: Integration).
    * Search for "Gemini Tool Bridge" and install.
    * Restart Home Assistant.
2.  **Manual Install:**
    * Copy `custom_components/gemini_tool_bridge` to your `/config/custom_components/` directory.
    * Restart Home Assistant.
3.  **Setup:**
    * Go to **Settings > Devices & Services > Add Integration**.
    * Search for **Gemini Tool Bridge**.
    * Follow the setup flow (no specific config required, it auto-discovers).

### Part 2: The Add-on
This runs the Python proxy server.

1.  **Add Local Add-on:**
    * Copy the `addon/` folder to your Home Assistant `/addons/gemini-live-bridge` directory (requires standard local add-on setup).
    * *Alternatively, if you publish this repo, users can add the repo URL to the Add-on Store.*
2.  **Configuration:**
    * In the Add-on "Configuration" tab, set your `gemini_api_key`.
3.  **Network:**
    * Ensure UDP Port `7000` is exposed/mapped.
4.  **Start:**
    * Start the Add-on and check the logs to ensure it connects to the Custom Component.

### Part 3: ESPHome Configuration
Flash your ESP32 with a configuration that streams audio to the Add-on's IP address.

* **Microphone:** Stream raw PCM to `Addon_IP:7000`.
* **Speaker:** Listen for raw PCM on `UDP:7001` (or your configured return port).

---

## ⚙️ Configuration

### Add-on Options (`config.yaml`)

| Option | Description | Required |
| :--- | :--- | :--- |
| `gemini_api_key` | Your Google AI Studio API Key. | ✅ Yes |

### Ports

* **7000 (UDP):** Incoming Audio from ESPHome.
* **7000 (TCP/HTTP):** Web Interface for monitoring and testing.
* **7001 (UDP):** Outgoing Audio to ESPHome (Speaker).

---

## 🎮 Web Interface
The Add-on includes a web dashboard for debugging.
Access it at: `http://<YOUR_HA_IP>:7000`

* **Microphone Test:** Stream audio from your browser mic to test Gemini without an ESP32.
* **Tool Test:** Manually execute Home Assistant commands (e.g., turn on lights) to verify the integration path.
* **Live Status:** View connection status and logs.

---

## 💡 Capabilities
The system exposes the following tools to Gemini automatically based on your exposed entities:

* **Control Devices:** "Turn on the kitchen lights", "Lock the front door".
* **Media Control:** "Pause the TV", "Volume up", "Play music".
* **Queries:** "What is the temperature in the bedroom?", "Is the garage door open?" (Uses `GetLiveContext`).
* **Todo Lists:** "Add milk to the shopping list".

---

## 🐛 Troubleshooting

* **"Component not found":** Ensure the folder structure is `custom_components/gemini_tool_bridge/` and you have restarted HA.
* **Audio Glitches:** Ensure your ESP32 has a strong WiFi connection. The Add-on logs will show buffer underruns.
* **Gemini 400 Errors:** Check your API Key and ensure you have access to the `gemini-2.0-flash-exp` (or configured model).

---

## 📜 License
[MIT License](LICENSE)