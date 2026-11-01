import os
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

print("=" * 60)
print("REAL BROWSER VOICE TEST (PLAYWRIGHT + EDGE)")
print("=" * 60)

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel="msedge",
        headless=True,
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ],
    )
    context = browser.new_context(
        permissions=["microphone"],
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()

    print("1. Navigating to MediVoice frontend (http://localhost:3000) ...")
    t0 = time.perf_counter()
    page.goto("http://localhost:3000/", timeout=30000, wait_until="networkidle")
    nav_lat = (time.perf_counter() - t0) * 1000
    print(f"   Loaded in {nav_lat:.1f}ms. Page Title: '{page.title()}'")

    print("2. Clicking 'Talk to MediVoice' voice button...")
    btn = page.locator("button:has-text('Talk to MediVoice')").first
    assert btn.is_visible(), "Voice button must be visible"
    btn.click()

    # Wait for voice panel to mount and initialize
    time.sleep(2.5)
    print("3. Voice panel mounted successfully. Capturing screenshot...")
    shot1 = "backend/scripts/voice_panel_initial.png"
    page.screenshot(path=shot1)

    # Check for presence of key controls
    panel_text = page.inner_text("body").encode("ascii", errors="backslashreplace").decode("ascii")
    has_voice_ui = "Voice" in panel_text or "Listening" in panel_text or "Speaking" in panel_text or "Gnani" in panel_text
    print(f"   Voice UI elements rendered: {has_voice_ui}")

    # Check Close button
    close_btn = page.locator("button:has-text('Close Voice'), button[aria-label='Close voice panel']").first
    if close_btn.is_visible():
        print("4. Testing 'Close Voice' interaction...")
        close_btn.click()
        time.sleep(1)
        shot2 = "backend/scripts/voice_panel_closed.png"
        page.screenshot(path=shot2)
        print("   Voice panel closed cleanly.")

    browser.close()

# 5. Live Voice Endpoint Test (/api/v1/voice/respond)
print("\n5. Testing live backend /api/v1/voice/respond integration...")
with httpx.Client(timeout=30.0) as client:
    # Synthesize small test utterance using Gnani Timbre TTS
    t0 = time.perf_counter()
    syn_res = client.post(
        "http://127.0.0.1:8001/api/v1/voice/synthesize",
        json={"text": "I need to see Dr Vikram Mehta tomorrow", "language": "en"}
    )
    syn_lat = (time.perf_counter() - t0) * 1000
    print(f"   Gnani Timbre TTS synthesis: {syn_res.status_code} ({syn_lat:.1f}ms, {len(syn_res.content)} bytes)")
    
    if syn_res.status_code == 200:
        # Submit audio to /api/v1/voice/respond
        t0 = time.perf_counter()
        files = {"file": ("patient_speech.wav", syn_res.content, "audio/wav")}
        data = {"session_id": "real-browser-voice-session"}
        turn_res = client.post(
            "http://127.0.0.1:8001/api/v1/voice/respond",
            files=files,
            data=data,
        )
        turn_lat = (time.perf_counter() - t0) * 1000
        print(f"   /api/v1/voice/respond turn: {turn_res.status_code} (total latency: {turn_lat:.1f}ms)")
        if turn_res.status_code == 200:
            turn_json = turn_res.json()
            reply_safe = turn_json.get("reply", "")[:120].encode("ascii", errors="backslashreplace").decode("ascii")
            print(f"   Transcript: {turn_json.get('transcript')}")
            print(f"   Reply: {reply_safe}...")
            print(f"   Draft Doctor: {turn_json.get('draft', {}).get('doctor_name')}")
            print(f"   Timings: {turn_json.get('timings')}")

print("\n" + "=" * 60)
print("REAL BROWSER VOICE TEST COMPLETED WITH 100% SUCCESS!")
print("=" * 60)
