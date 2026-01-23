import logging
import traceback
from aiohttp import web, WSMsgType, ClientSession

# from audio import WEB_INPUT_RATE
from context import get_context, HA_URL, HA_TOKEN
from intent_tools import IntentToolHandler, get_intent_tools

logger = logging.getLogger(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Gemini Live Proxy</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
        h1, h3, p { text-align: center; }
        button { padding: 10px 20px; font-size: 1rem; cursor: pointer; margin: 5px; }
        .section { border: 1px solid #ccc; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        #status { margin-top: 20px; color: #666; text-align: center; }
        .recording { background-color: #ff4444; color: white; }
        textarea, input[type="text"] { width: 100%; box-sizing: border-box; font-family: monospace; padding: 8px; margin-bottom: 10px; }
        select { padding: 8px; font-size: 1rem; margin-bottom: 10px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <h1>Gemini Live Proxy</h1>

    <div class="section">
        <h3>Connection Mode</h3>
        <select id="connectionMode">
            <option value="bridge" selected>Bridge (Addon Proxies)</option>
            <option value="direct">Direct Connect (Device to Google)</option>
        </select>
        <div id="apiKeySection" class="hidden" style="text-align: left;">
            <label for="apiKey">Google AI API Key:</label>
            <input type="text" id="apiKey" placeholder="Enter your API Key">
            <button id="getSessionBtn">Get Direct Session</button>
        </div>
    </div>

    <div class="section">
        <h3>Microphone Input</h3>
        <p>Stream your browser microphone to Gemini.</p>
        <div style="text-align: center;">
            <button id="startBtn">Start Mic</button>
            <button id="stopBtn" disabled>Stop Mic</button>
        </div>
        <div id="status">Ready</div>
    </div>

    <div id="directContextSection" class="section hidden">
        <h3>Direct Connect Session Details</h3>
        <div style="text-align: left;">
            <strong>Context:</strong>
            <pre id="contextOutput" style="background: #f4f4f4; padding: 10px; border-radius: 4px; min-height: 40px; overflow: auto; max-height: 30vh;">...</pre>
            <strong>Tools:</strong>
            <pre id="directToolsOutput" style="background: #f4f4f4; padding: 10px; border-radius: 4px; min-height: 40px; overflow: auto; max-height: 30vh;">...</pre>
        </div>
    </div>

    <div class="section">
        <h3>Manual Tool Test (Bridge Mode Only)</h3>
        <p>Select a tool and provide JSON arguments to test execution.</p>
        
        <select id="toolName">
            <option value="ProxySetState">ProxySetState (On/Off/Lock/Open)</option>
            <option value="HassLightSet">HassLightSet (Brightness/Color)</option>
            <option value="ProxyMediaControl">ProxyMediaControl (Play/Pause/Next)</option>
            <option value="ProxyControlVolume">ProxyControlVolume (Set/Increase/Decrease)</option>
            <option value="ProxySetMute">ProxySetMute</option>
            <option value="HassMediaSearchAndPlay">HassMediaSearchAndPlay</option>
            <option value="HassFanSetSpeed">HassFanSetSpeed</option>
            <option value="HassStartTimer">HassStartTimer</option>
            <option value="HassCancelTimer">HassCancelTimer</option>
            <option value="ProxyAdjustTimer">ProxyAdjustTimer (Increase/Decrease)</option>
            <option value="ProxyPauseResumeTimer">ProxyPauseResumeTimer</option>
            <option value="HassBroadcast">HassBroadcast</option>
            <option value="GetLiveContext">GetLiveContext</option>
            <option value="HassIntentRaw">HassIntentRaw</option>
        </select>
        <br/>
        
        <textarea id="toolArgs" rows="5" placeholder='{"state": "on", "name": "Kitchen Lights"}'></textarea>
        <br/><br/>
        <button onclick="executeTool()">Execute Tool</button>
        
        <div style="text-align: left; margin-top: 15px;">
            <strong>Result:</strong>
            <pre id="toolOutput" style="background: #f4f4f4; padding: 10px; border-radius: 4px; min-height: 40px;">...</pre>
        </div>
    </div>

    <script>
        // --- State Management ---
        let audioContext;
        let websocket;
        let processor;
        let source;
        let isRecording = false;
        let nextStartTime = 0;
        let directSessionToken = null;

        // --- DOM Elements ---
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const status = document.getElementById('status');
        const connectionModeSelect = document.getElementById('connectionMode');
        const apiKeySection = document.getElementById('apiKeySection');
        const getSessionBtn = document.getElementById('getSessionBtn');
        const apiKeyInput = document.getElementById('apiKey');
        const directContextSection = document.getElementById('directContextSection');
        const contextOutput = document.getElementById('contextOutput');
        const directToolsOutput = document.getElementById('directToolsOutput');

        // --- Event Listeners ---
        connectionModeSelect.addEventListener('change', () => {
            const isDirect = connectionModeSelect.value === 'direct';
            apiKeySection.classList.toggle('hidden', !isDirect);
            directContextSection.classList.toggle('hidden', !isDirect);
            if (!isDirect) directSessionToken = null; // Clear token when switching away
        });

        getSessionBtn.addEventListener('click', createDirectSession);
        startBtn.addEventListener('click', startMicrophone);
        stopBtn.addEventListener('click', stopRecording);
        window.addEventListener('load', connectWebSocket);


        // --- Core Functions ---
        async function createDirectSession() {
            const apiKey = apiKeyInput.value;
            if (!apiKey) {
                alert("Please enter your Google AI API Key.");
                return;
            }
            status.innerText = "Requesting direct session...";
            try {
                const response = await fetch('/session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: apiKey })
                });

                const data = await response.json();

                if (data.success) {
                    directSessionToken = data.token;
                    contextOutput.innerText = data.context;
                    directToolsOutput.innerText = JSON.stringify(data.tools, null, 2);
                    status.innerText = "Direct session ready. You can now start the mic.";
                    // Re-connect the websocket with the new token info
                    connectWebSocket();
                } else {
                    throw new Error(data.error || "Failed to get session.");
                }
            } catch (err) {
                console.error("Session creation failed:", err);
                status.innerText = "Error: " + err.message;
                directSessionToken = null;
            }
        }

        async function startMicrophone() {
            if (connectionModeSelect.value === 'direct' && !directSessionToken) {
                alert("Please get a direct session token before starting the microphone.");
                return;
            }
            await initAudio();
            // Ensure websocket is connected/reconnected
            if (!websocket || websocket.readyState !== WebSocket.OPEN) {
                await connectWebSocket();
            }
            // Wait for websocket to be open
            if (websocket.readyState !== WebSocket.OPEN) {
                await new Promise(resolve => websocket.onopen = () => resolve());
            }

            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                startRecording(stream);
            } catch (err) {
                console.error("Mic error:", err);
                status.innerText = "Error: " + err.message;
            }
        }

        async function connectWebSocket() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.close();
            }

            return new Promise((resolve, reject) => {
                websocket = new WebSocket('ws://' + window.location.host + '/ws');
                websocket.binaryType = 'arraybuffer';

                websocket.onopen = () => {
                    status.innerText = "Connected to Addon.";
                    const config = {
                        mode: connectionModeSelect.value,
                        token: directSessionToken
                    };
                    websocket.send(JSON.stringify(config));
                    resolve();
                };

                websocket.onmessage = async (event) => {
                    if (typeof event.data === 'string') {
                        console.log("Text message received:", event.data);
                        return;
                    }
                    await initAudio();
                    playAudio(event.data);
                };

                websocket.onclose = () => {
                    stopRecording(); // This also updates button states
                    status.innerText = "Disconnected from Addon.";
                };

                websocket.onerror = (err) => {
                    console.error("WebSocket Error:", err);
                    status.innerText = "WebSocket connection error.";
                    reject(err);
                }
            });
        }

        function startRecording(stream) {
            isRecording = true;
            source = audioContext.createMediaStreamSource(stream);
            processor = audioContext.createScriptProcessor(4096, 1, 1);
            processor.onaudioprocess = (e) => {
                if (!isRecording) return;
                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                    let s = Math.max(-1, Math.min(1, inputData[i]));
                    pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    websocket.send(pcmData.buffer);
                }
            };
            source.connect(processor);
            processor.connect(audioContext.destination);
            startBtn.disabled = true; stopBtn.disabled = false; startBtn.classList.add('recording');
            status.innerText = "Recording...";
        }

        function stopRecording() {
            isRecording = false;
            if (source) {
                // Stop the media stream tracks to turn off the mic indicator
                source.mediaStream.getTracks().forEach(track => track.stop());
                source.disconnect();
                source = null;
            }
            if (processor) { processor.disconnect(); processor = null; }
            startBtn.disabled = false; stopBtn.disabled = true; startBtn.classList.remove('recording');
            status.innerText = "Mic Stopped.";
            nextStartTime = 0;
        }

        async function initAudio() {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
            }
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }
        }

        function playAudio(arrayBuffer) {
            if (!audioContext) return;
            const data = new Int16Array(arrayBuffer);
            const floatData = new Float32Array(data.length);
            for (let i = 0; i < data.length; i++) { floatData[i] = data[i] / 32768.0; }
            const buffer = audioContext.createBuffer(1, floatData.length, 48000);
            buffer.getChannelData(0).set(floatData);
            const sourceNode = audioContext.createBufferSource();
            sourceNode.buffer = buffer;
            sourceNode.connect(audioContext.destination);
            const currentTime = audioContext.currentTime;
            if (nextStartTime < currentTime) { nextStartTime = currentTime; }
            sourceNode.start(nextStartTime);
            nextStartTime += buffer.duration;
        }

        // --- Tool Testing ---
        async function executeTool() {
            const name = document.getElementById('toolName').value;
            const argsStr = document.getElementById('toolArgs').value || "{}";
            const output = document.getElementById('toolOutput');

            output.innerText = "Executing...";

            try {
                // Validate JSON first
                let args = {};
                if (argsStr.trim()) {
                    args = JSON.parse(argsStr);
                }

                const response = await fetch('/tool', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, args: args })
                });

                const result = await response.text();
                output.innerText = result;
            } catch (err) {
                output.innerText = "Error: " + err.message;
            }
        }
    </script>
</body>
</html>
"""

class WebHandler:
    def __init__(self, proxy):
        self.proxy = proxy
        self.tool_handler = IntentToolHandler(self.proxy.ha_client)

    async def index_handler(self, request: web.Request):
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def session_handler(self, request: web.Request):
        """Proxy the session request to the Home Assistant component."""
        try:

            url = f"{HA_URL}/gemini_live/session"
            headers = {
                "Authorization": f"Bearer {HA_TOKEN}",
                "Content-Type": "application/json",
            }

            async with ClientSession() as session:
                async with session.post(url, headers=headers) as resp:
                    if resp.status == 200:
                        session_data = await resp.json()
                        return web.json_response(session_data)
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to create session: {resp.status} {error_text}")
                        return web.json_response({"success": False, "error": error_text}, status=resp.status)

        except Exception as e:
            logger.error(f"session_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.json_response({"success": False, "error": str(e)}, status=500)

    async def websocket_handler(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.proxy.web_clients.add(ws)
        logger.info("Web Client Connected")

        try:
            # First message is configuration
            config_msg = await ws.receive_json()
            mode = config_msg.get("mode", "bridge")
            token = config_msg.get("token")

            # Use the ws object itself as the key for web clients
            session = self.proxy.get_session_for_client(ws, mode, token)

            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    await session.process_incoming_audio(msg.data)
                elif msg.type == WSMsgType.TEXT:
                     logger.warning(f"Received unexpected text message from web client: {msg.data}")
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"Websocket connection closed with exception {ws.exception()}")
                    break
        finally:
            self.proxy.remove_session_for_client(ws)
            self.proxy.web_clients.remove(ws)
            logger.info("Web Client Disconnected")

        return ws

    async def tool_test_handler(self, request: web.Request):
        """Handle manual tool execution requests."""
        try:
            data = await request.json()
            name = data.get("name")
            args = data.get("args", {})
            result = await self.tool_handler.handle_tool_call(name, args)
            return web.Response(text=str(result))
        except Exception as e:
            return web.Response(text=f"Error: {e}", status=500)
        
    async def tool_list_handler(self, request: web.Request):
        """List all available tools."""
        try:
            tools_data = []
            tool_objs = get_intent_tools()
            for tool in tool_objs:
                funcs = tool.function_declarations or []
                for func in funcs:
                     tools_data.append({
                         "name": func.name,
                         "description": func.description,
                         "parameters": func.parameters_json_schema
                     })
            
            return web.json_response({"tools": tools_data})
        except Exception as e:
            logger.error(f"tool_list_handler error: {e}")
            return web.Response(text=f"Error: {e}", status=500)
        
    async def entity_list_handler(self, request: web.Request):
        """List all available entities."""
        try:
            entities = await get_context(raw=True)
            return web.json_response(entities)
        except Exception as e:
            logger.error(f"entity_list_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.Response(text=f"Error: {e}", status=500)
        
    async def entities_handler(self, request: web.Request):
        """List all available entities (grouped context)."""
        try:
            entities = await get_context(raw=False)
            return web.Response(text=str(entities))
        except Exception as e:
            logger.error(f"entities_handler error: {e}")
            error_trace = traceback.format_exc()
            logger.error(f"Traceback: {error_trace}")
            return web.Response(text=f"Error: {e}", status=500)