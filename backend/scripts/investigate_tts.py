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

print("=" * 60)
print("INVESTIGATING GNANI TIMBRE TTS LATENCY")
print("=" * 60)

# 1. Connection overhead: New client vs Persistent client
payload_short = {
    "text": "Dr. Rajesh Sharma is available tomorrow at 9:00 AM.",
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

print("\n--- Test 1: New Client vs Persistent Client (Connection Reuse) ---")
# Call 1 with fresh client
t0 = time.perf_counter()
with httpx.Client(timeout=20.0) as client:
    r1 = client.post(url, headers=headers, json=payload_short)
lat_fresh = (time.perf_counter() - t0) * 1000
print(f"Fresh client (TCP+TLS+Generation+Download): {lat_fresh:.1f}ms | Audio bytes: {len(r1.content)}")

# Call 2 & 3 with persistent client
with httpx.Client(timeout=20.0) as persistent_client:
    # Warmup / handshake
    t0 = time.perf_counter()
    r2 = persistent_client.post(url, headers=headers, json=payload_short)
    lat_p1 = (time.perf_counter() - t0) * 1000
    
    # Reused connection
    t0 = time.perf_counter()
    r3 = persistent_client.post(url, headers=headers, json=payload_short)
    lat_p2 = (time.perf_counter() - t0) * 1000
    print(f"Persistent client (1st call with TLS): {lat_p1:.1f}ms")
    print(f"Persistent client (2nd call reused connection): {lat_p2:.1f}ms (Connection savings: {lat_fresh - lat_p2:.1f}ms)")

# 2. Text length impact (Word count)
print("\n--- Test 2: Word Count Impact on Generation Time ---")
phrases = [
    ("Very Concise (8 words)", "Dr. Sharma is available tomorrow at 9:00 AM."),
    ("Concise (16 words)", "Dr. Rajesh Sharma is available in Cardiology tomorrow at 9:00 AM. Would you like this slot?"),
    ("Verbose (37 words)", "I would be pleased to assist you with scheduling an appointment with Dr. Rajesh Sharma in Cardiology at Aarogya One Hospital. For tomorrow, he has an open slot at 9:00 AM. Would you like to reserve this?"),
    ("Very Verbose (62 words)", "Hello! Welcome to Aarogya One Hospital. I can certainly help you book an appointment with our specialist, Dr. Rajesh Sharma, in the department of Cardiology. We have checked our real-time database and found an available slot for tomorrow at 9:00 AM. Please let me know if you would like me to reserve this appointment slot for you right now."),
]

with httpx.Client(timeout=30.0) as client:
    for label, text in phrases:
        p = dict(payload_short)
        p["text"] = text
        t0 = time.perf_counter()
        # Stream response to measure TTFB (generation time) vs download time
        with client.stream("POST", url, headers=headers, json=p) as resp:
            ttfb = (time.perf_counter() - t0) * 1000
            content = resp.read()
            total_time = (time.perf_counter() - t0) * 1000
            dl_time = total_time - ttfb
            print(f"[{label}] TTFB (Provider gen): {ttfb:.1f}ms | Download: {dl_time:.1f}ms | Total: {total_time:.1f}ms | Size: {len(content):,} bytes")

# 3. Sample Rate Impact (48kHz vs 16kHz)
print("\n--- Test 3: Sample Rate Impact (48000 Hz vs 16000 Hz) ---")
with httpx.Client(timeout=30.0) as client:
    for sr in [48000, 24000, 16000, 8000]:
        p = dict(payload_short)
        p["audio_config"]["sample_rate"] = sr
        t0 = time.perf_counter()
        resp = client.post(url, headers=headers, json=p)
        tot = (time.perf_counter() - t0) * 1000
        print(f"Sample Rate {sr} Hz: Status {resp.status_code} | Total: {tot:.1f}ms | Size: {len(resp.content):,} bytes")

