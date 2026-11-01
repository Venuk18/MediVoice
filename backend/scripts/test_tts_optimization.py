import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv("backend/.env")
api_key = os.getenv("GNANI_API_KEY")
api_base = os.getenv("GNANI_API_BASE", "https://api.vachana.ai").rstrip("/")
url = f"{api_base}/api/v1/tts/inference"
headers = {
    "X-API-Key-ID": api_key,
    "Content-Type": "application/json",
    "User-Agent": "MediVoice-AI-TimbreClient/1.0",
}

# Baseline: Verbose text + 48kHz + fresh client
verbose_text = "I would be pleased to assist you with scheduling an appointment with Dr. Vikram Mehta in General Medicine. For tomorrow, he has an open slot at 9:00 AM. Would you like to reserve this slot?"
p_baseline = {
    "text": verbose_text,
    "voice": "Shivani",
    "model": "timbre-v3.0",
    "language": "en-IN",
    "speed": 1.0,
    "audio_config": {
        "container": "wav",
        "encoding": "linear_pcm",
        "sample_rate": 48000,
        "num_channels": 1,
        "sample_width": 2,
    },
}

t0 = time.perf_counter()
with httpx.Client(timeout=20.0) as client:
    r_base = client.post(url, headers=headers, json=p_baseline)
lat_baseline = (time.perf_counter() - t0) * 1000
print(f"BASELINE (Verbose text + 48kHz + New client): {lat_baseline:.1f}ms | Size: {len(r_base.content):,} bytes")

# Optimized: Concise text + 16kHz + Persistent client
concise_text = "Dr. Vikram Mehta is available tomorrow at 9:00 AM. Would you like to reserve this slot?"
p_optimized = {
    "text": concise_text,
    "voice": "Shivani",
    "model": "timbre-v3.0",
    "language": "en-IN",
    "speed": 1.0,
    "audio_config": {
        "container": "wav",
        "encoding": "linear_pcm",
        "sample_rate": 16000,
        "num_channels": 1,
        "sample_width": 2,
    },
}

# Warmup connection
persistent_client = httpx.Client(timeout=20.0)
persistent_client.post(url, headers=headers, json=p_optimized)

t0 = time.perf_counter()
r_opt = persistent_client.post(url, headers=headers, json=p_optimized)
lat_optimized = (time.perf_counter() - t0) * 1000
persistent_client.close()

print(f"OPTIMIZED (Concise text + 16kHz + Persistent client): {lat_optimized:.1f}ms | Size: {len(r_opt.content):,} bytes")
savings = lat_baseline - lat_optimized
pct = (savings / lat_baseline) * 100
print(f"TTS LATENCY REDUCTION: {savings:.1f}ms saved ({pct:.1f}% faster!)")

