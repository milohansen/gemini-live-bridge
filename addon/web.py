import logging
from aiohttp import web, WSMsgType

from tools import fetch_entities_via_http, fetch_tools_via_http

logger = logging.getLogger(__name__)

# Move the HTML template here to keep the main file clean
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Gemini Live Proxy</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; text-align: center; }
        button { padding: 10px 20px; font-size: 1rem; cursor: pointer; margin: 5px; }
        .section { border: 1px solid #ccc; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        #status { margin-top: 20px; color: #666; }
        .recording { background-color: #ff4444; color: white; }
        textarea { width: 100%; font-family: monospace; }
        select { padding: 8px; font-size: 1rem; margin-bottom: 10px; }
    </style>
</head>
<body>
    <h1>Gemini Live Proxy</h1>
    
    <div class="section">
        <h3>Microphone Input</h3>
        <p>Stream your browser microphone to Gemini.</p>
        <button id="startBtn">Start Mic</button>
        <button id="stopBtn" disabled>Stop Mic</button>
        <div id="status">Ready</div>
    </div>

    <div class="section">
        <h3>Manual Tool Test</h3>
        <p>Select a tool and provide JSON arguments to test execution.</p>
        
        <select id="toolName">
            <option value="HassSetState">HassSetState (On/Off/Lock)</option>
            <option value="HassLightSet">HassLightSet (Brightness/Color)</option>
            <option value="HassMediaControl">HassMediaControl (Play/Pause)</option>
            <option value="HassControlVolume">HassControlVolume</option>
            <option value="HassManageTodoList">HassManageTodoList</option>
            <option value="GetLiveContext">GetLiveContext</option>
            <option value="HassBroadcast">HassBroadcast</option>
            <option value="HassFanSetSpeed">HassFanSetSpeed</option>
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

    <div class="section">
        <h3>Available Tools</h3>
        <p>Fetch the list of tools currently available to Gemini.</p>
        <button onclick="fetchTools()">List Tools</button>
        <div style="text-align: left; margin-top: 15px;">
            <strong>Result:</strong>
            <pre id="toolsOutput" style="background: #f4f4f4; padding: 10px; border-radius: 4px; min-height: 40px;">...</pre>
        </div>
    </div>

    <script>
        // --- Tool Testing Logic ---
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

        async function fetchTools() {
            const output = document.getElementById('toolsOutput');
            output.innerText = "Fetching...";
            try {
                const response = await fetch('/tools');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                output.innerText = JSON.stringify(data, null, 2);
            } catch (err) {
                output.innerText = "Error: " + err.message;
            }
        }

        // --- Audio Logic ---
        let audioContext;
        let websocket;
        let processor;
        let source;
        let isRecording = false;
        let nextStartTime = 0;
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const status = document.getElementById('status');

        async function initAudio() {
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)({sampleRate: 48000});
            }
            if (audioContext.state === 'suspended') {
                await audioContext.resume();
            }
        }

        async function connectWebSocket() {
            if (websocket && websocket.readyState === WebSocket.OPEN) return;
            websocket = new WebSocket('ws://' + window.location.host + '/ws');
            websocket.binaryType = 'arraybuffer';
            websocket.onopen = () => { status.innerText = "Connected to Proxy"; };
            websocket.onmessage = async (event) => {
                await initAudio(); 
                playAudio(event.data);
            };
            websocket.onclose = () => {
                stopRecording();
                status.innerText = "Disconnected";
            };
        }
        window.addEventListener('load', () => {
            connectWebSocket();
        });
        startBtn.onclick = async () => {
            await initAudio();
            await connectWebSocket();
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                startRecording(stream);
            } catch (err) {
                console.error(err);
                status.innerText = "Error: " + err.message;
            }
        };
        stopBtn.onclick = stopRecording;
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
        }
        function stopRecording() {
            isRecording = false;
            if (source) { source.disconnect(); source = null; }
            if (processor) { processor.disconnect(); processor = null; }
            startBtn.disabled = false; stopBtn.disabled = true; startBtn.classList.remove('recording');
            status.innerText = "Mic Stopped (Still Listening)";
            nextStartTime = 0;
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
    </script>
</body>
</html>
"""

class WebHandler:
    def __init__(self, proxy):
        self.proxy = proxy

    async def index_handler(self, request):
        return web.Response(text=INDEX_HTML, content_type="text/html")

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.proxy.web_clients.add(ws)
        if not self.proxy.connection_active.is_set():
             logger.info("Web Client connected: Activating Gemini Session")
             self.proxy.connection_active.set()
             
        logger.info("Web Client Connected")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.BINARY:
                    # Web client sends Int16 PCM (48kHz)
                    await self.proxy.process_incoming_audio(msg.data, self.proxy.WEB_INPUT_RATE)
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"Websocket connection closed with exception {ws.exception()}")
        finally:
            self.proxy.web_clients.remove(ws)
            logger.info("Web Client Disconnected")

        return ws

    async def tool_test_handler(self, request):
        """Handle manual tool execution requests."""
        try:
            data = await request.json()
            name = data.get("name")
            args = data.get("args", {})
            result = await self.proxy.tool_handler.handle_tool_call(name, args)
            return web.Response(text=str(result))
        except Exception as e:
            return web.Response(text=f"Error: {e}", status=500)
        
    async def tool_list_handler(self, request):
        """List all available tools."""
        try:
            tools = await fetch_tools_via_http()
            return web.json_response(tools)
        except Exception as e:
            return web.Response(text=f"Error: {e}", status=500)
        
    async def entity_list_handler(self, request):
        """List all available entities."""
        try:
            entities = await fetch_entities_via_http(True)
            return web.json_response(entities)
        except Exception as e:
            return web.Response(text=f"Error: {e}", status=500)
        
    async def entities_handler(self, request):
        """List all available entities."""
        try:
            entities = await fetch_entities_via_http()
            return web.Response(text=str(entities))
        except Exception as e:
            return web.Response(text=f"Error: {e}", status=500)