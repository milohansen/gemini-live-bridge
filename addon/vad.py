import os
import numpy as np
import onnxruntime

from logger import logger

# VAD Config
VAD_MODEL_PATH = "silero_vad.onnx"
# Silero VAD works best with chunks of 512, 1024, or 1536 samples (at 16kHz)
VAD_CHUNK_SIZE_SAMPLES = 512
VAD_CHUNK_SIZE_BYTES = VAD_CHUNK_SIZE_SAMPLES * 2  # 16-bit audio = 2 bytes/sample

class VADWrapper:
    def __init__(self):
        if not os.path.exists(VAD_MODEL_PATH):
            logger.info("Downloading Silero VAD model (V5)...")
            import urllib.request

            urllib.request.urlretrieve(
                "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx",
                VAD_MODEL_PATH,
            )

        # Suppress onnxruntime warnings
        sess_options = onnxruntime.SessionOptions()
        sess_options.log_severity_level = 3
        self.session = onnxruntime.InferenceSession(VAD_MODEL_PATH, sess_options)
        self.reset_states()

    def reset_states(self):
        # Silero VAD V5 uses a single state tensor of shape (2, 1, 128)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def is_speech(self, audio_chunk_16k):
        audio_int16 = np.frombuffer(audio_chunk_16k, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        # Protect against empty or tiny chunks
        if len(audio_float32) < 32:
            return 0.0

        input_data = {
            "input": audio_float32[np.newaxis, :],
            "sr": np.array([16000], dtype=np.int64),
            "state": self._state,
        }

        # Run inference: returns [output, state]
        out, state = self.session.run(None, input_data)
        self._state = state
        return out[0][0]
