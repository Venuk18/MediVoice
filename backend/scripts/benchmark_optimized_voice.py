import io
import json
import os
import sys
import time
import httpx

sys.path.insert(0, "backend")
from app.services.speech.tts_service import GnaniTimbreTTS

BACKEND_URL = "http://127.0.0.1:8001/api/v1/voice/respond"

BENCHMARK_SCENARIOS = [
    {
        "turn": 1,
        "name": "Predictable Cardiologist Search",
        "prompt": "Search for a cardiologist",
        "lang": "en",
        "expected_tool": "search_doctors",
    },
    {
        "turn": 2,
        "name": "Predictable General Physician Search",
        "prompt": "I need Dr. Vikram Mehta",
        "lang": "en",
        "expected_tool": "search_doctors",
    },
    {
        "turn": 3,
        "name": "Available Slots Lookup",
        "prompt": "Check available slots",
        "lang": "en",
        "setup_doctor": "doc-sharma-1",
        "expected_tool": "get_available_slots",
    },
    {
        "turn": 4,
        "name": "Hospital Insurance Inquiry",
        "prompt": "Do you accept Star Health Insurance?",
        "lang": "en",
        "expected_tool": "search_hospital_insurance",
    },
    {
        "turn": 5,
        "name": "Complex Clinical Inquiry & Telugu Conversation",
        "prompt": "\u0c28\u0c3e\u0c15\u0c41 \u0c17\u0c41\u0c02\u0c21\u0c46 \u0c28\u0c4a\u0c2a\u0c4d\u0c2a\u0c3f\u0c17\u0c3e \u0c09\u0c02\u0c26\u0c3f, \u0c15\u0c3e\u0c30\u0c4d\u0c21\u0c3f\u0c2f\u0c3e\u0c32\u0c1c\u0c3f\u0c38\u0c4d\u0c1f\u0c4d \u0c15\u0c3e\u0c35\u0c3e\u0c32\u0c3f",
        "lang": "te",
        "expected_tool": "search_doctors",
    },
]

def run_benchmark():
    tts_generator = GnaniTimbreTTS()
    print("=" * 75)
    print("MediVoice AI - Live Voice Benchmark (Gemini 3.5 Flash-Lite Optimized)")
    print("=" * 75)
    print(f"Target Endpoint: {BACKEND_URL}")
    print(f"Model ID: gemini-3.5-flash-lite (Thinking: low)")
    print()

    results = []

    for item in BENCHMARK_SCENARIOS:
        turn_num = item["turn"]
        name = item["name"]
        prompt = item["prompt"]
        lang = item["lang"]
        session_id = f"bench-opt-turn-{turn_num}-{int(time.time())}"

        print(f"--- [Turn {turn_num}] {name} ---")
        prompt_display = prompt.encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"Input Prompt: '{prompt_display}' ({lang})")

        # Step 1: Generate real input WAV speech using Gnani Timbre
        t_prep_start = time.perf_counter()
        input_audio_bytes = tts_generator.synthesize(text=prompt, language=lang)
        prep_ms = (time.perf_counter() - t_prep_start) * 1000
        print(f"Generated input voice audio ({len(input_audio_bytes)} bytes) in {prep_ms:.1f} ms")

        # If turn 3 requires doctor setup in session, set up doctor first
        if item.get("setup_doctor"):
            setup_payload = {
                "message": "I want Dr. Rajesh Sharma",
                "session_id": session_id,
            }
            try:
                httpx.post("http://127.0.0.1:8001/api/v1/agent/chat", json=setup_payload, timeout=10.0)
            except Exception as e:
                print(f"Note on setup: {e}")

        # Step 2: Send live voice request to FastAPI endpoint
        files = {
            "file": ("patient_speech.wav", io.BytesIO(input_audio_bytes), "audio/wav"),
        }
        data = {
            "session_id": session_id,
            "language": lang,
        }

        t_req_start = time.perf_counter()
        response = httpx.post(BACKEND_URL, files=files, data=data, timeout=45.0)
        round_trip_ms = (time.perf_counter() - t_req_start) * 1000

        if response.status_code != 200:
            print(f"ERROR: HTTP {response.status_code}: {response.text}")
            continue

        resp_json = response.json()
        timings = resp_json.get("timings", {})
        transcript = resp_json.get("transcript", "")
        transcript_display = transcript.encode("ascii", errors="backslashreplace").decode("ascii")
        reply = resp_json.get("reply", "")
        reply_display = reply[:120].replace("\n", " ").encode("ascii", errors="backslashreplace").decode("ascii")
        has_tts_audio = resp_json.get("tts_available", False)
        audio_b64_len = len(resp_json.get("audio_base64") or "")

        stt_ms = timings.get("stt_ms", 0.0)
        agent_ms = timings.get("agent_ms", 0.0)
        initial_gemini_request_ms = timings.get("initial_gemini_request_ms", 0.0)
        tool_router_ms = timings.get("tool_router_ms", timings.get("tool_ms", 0.0))
        followup_gemini_request_ms = timings.get("followup_gemini_request_ms", 0.0)
        gemini_calls_count = timings.get("gemini_calls_count", 0)
        tts_ms = timings.get("tts_ms", 0.0)
        total_turn_ms = timings.get("total_turn_ms", round_trip_ms)
        first_audible_response_ms = timings.get("first_audible_response_ms", total_turn_ms)

        print(f"Transcript recognized: '{transcript_display}'")
        print(f"Assistant Reply: '{reply_display}...'")
        print(f"Audio Playback: {has_tts_audio} ({audio_b64_len} Base64 chars)")
        print(f"Sub-stage Timings:")
        print(f"  - Prisma STT: {stt_ms:.1f} ms")
        print(f"  - Gemini Calls: {gemini_calls_count}")
        print(f"  - Initial Gemini Req: {initial_gemini_request_ms:.1f} ms")
        print(f"  - Tool Router: {tool_router_ms:.1f} ms")
        print(f"  - Follow-up Gemini Req: {followup_gemini_request_ms:.1f} ms")
        print(f"  - Total Agent Ms: {agent_ms:.1f} ms")
        print(f"  - Timbre TTS: {tts_ms:.1f} ms")
        print(f"  - Total Turn / First Audible Response: {first_audible_response_ms:.1f} ms")
        print()

        results.append({
            "turn": turn_num,
            "name": name,
            "prompt": prompt,
            "lang": lang,
            "transcript": transcript,
            "reply": reply,
            "stt_ms": stt_ms,
            "gemini_calls_count": gemini_calls_count,
            "initial_gemini_request_ms": initial_gemini_request_ms,
            "tool_router_ms": tool_router_ms,
            "followup_gemini_request_ms": followup_gemini_request_ms,
            "agent_ms": agent_ms,
            "tts_ms": tts_ms,
            "total_turn_ms": total_turn_ms,
            "first_audible_response_ms": first_audible_response_ms,
        })

    # Save benchmark results to JSON
    out_path = "backend/benchmark_voice_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("=" * 75)
    print("Benchmark Completed Successfully. Results written to", out_path)
    print("=" * 75)

if __name__ == "__main__":
    run_benchmark()

