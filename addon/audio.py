import numpy as np
from scipy import signal as scipy_signal

# Audio Config
ESP_INPUT_RATE = 32000  # ESP32 P4 Native
GEMINI_INPUT_RATE = 16000
GEMINI_OUTPUT_RATE = 24000
ESP_OUTPUT_RATE = 48000
WEB_INPUT_RATE = 48000  # Standard browser mic rate (approx)

def resample_audio(self, audio_data, src_rate, dst_rate):
    if src_rate == dst_rate:
        return audio_data

    audio_np = np.frombuffer(audio_data, dtype=np.int16)
    num_samples = int(len(audio_np) * dst_rate / src_rate)
    resampled_np = scipy_signal.resample(audio_np, num_samples)
    return resampled_np.astype(np.int16).tobytes() # type: ignore
