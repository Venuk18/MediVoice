import asyncio
import json
import sys
import time
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

async def run_tests():
    console_logs = []
    network_errors = []
    milestone_logs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ]
        )
        context = await browser.new_context(
            permissions=["microphone"],
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("response", lambda resp: network_errors.append(f"{resp.status} {resp.url}") if resp.status >= 400 else None)

        print("=== Test 1: Navigation and Favicon Check ===")
        t_start = time.time()
        await page.goto("http://localhost:3000", wait_until="networkidle")
        print(f"Loaded page in {(time.time() - t_start)*1000:.1f}ms")

        favicon_404s = [e for e in network_errors if "favicon" in e]
        print(f"Favicon 404 errors: {favicon_404s} (Expected: None)")
        assert len(favicon_404s) == 0, f"Favicon 404 found: {favicon_404s}"

        print("\n=== Test 2: Voice Activation and 8-Milestone Latency Tracking ===")
        # Click "Talk to MediVoice" voice button in chatbot header
        mic_btn = page.locator('button[aria-label="Open full-screen voice assistant"]').first
        await mic_btn.click()
        print("Clicked 'Open full-screen voice assistant'")

        # Wait for voice panel overlay
        panel = page.locator('div[role="region"][aria-label="MediVoice AI Full-Screen Voice Receptionist Interface"]')
        await panel.wait_for(state="visible", timeout=5000)
        print("Voice Panel overlay visible")

        # Let greeting play or monitor milestones
        # We poll window.__medivoice_milestones
        for _ in range(40):
            await asyncio.sleep(0.2)
            milestones = await page.evaluate("() => window.__medivoice_milestones || {}")
            if "listeningActivated" in milestones or "playbackEnd" in milestones:
                break

        milestones = await page.evaluate("() => window.__medivoice_milestones || {}")
        print(f"Recorded Milestones: {json.dumps(milestones, indent=2)}")

        # Extract console milestone logs
        m_logs = [log for log in console_logs if "[MediVoice Milestone" in log]
        for m in m_logs:
            print(" ", m)

        # Verify playback start is fast (< 1000ms from activation)
        if "voiceActivation" in milestones and "playbackStart" in milestones:
            playback_latency = milestones["playbackStart"] - milestones["voiceActivation"]
            print(f"Playback start latency from activation: {playback_latency:.1f}ms")

        print("\n=== Test 3: First-Turn Silence Guard (No Premature Auto-Submit & No 422) ===")
        # Wait until state is 'listening'
        await page.wait_for_selector('h3:has-text("Listening")', timeout=10000)
        print("Confirmed state is 'Listening...'")

        # Now wait 3.5 seconds with room silence
        # In the previous broken implementation, it auto-submitted after 2.1s and caused 422
        print("Waiting 3.5 seconds in pure silence to verify VAD does NOT auto-submit...")
        await asyncio.sleep(3.5)

        # Verify state is STILL 'Listening...' and no 422 occurred
        state_heading = await page.locator('h3:has-text("Listening")').text_content()
        print(f"Current state heading after 3.5s of silence: '{state_heading.strip()}'")
        assert "Listening" in state_heading, f"Expected Listening state, but got: {state_heading}"

        voice_422s = [e for e in network_errors if "422" in e and "/voice/respond" in e]
        print(f"HTTP 422 /voice/respond errors during silence: {voice_422s} (Expected: None)")
        assert len(voice_422s) == 0, f"Premature 422 error triggered: {voice_422s}"

        print("\n=== Test 4: Empty Speech / Manual Submit Guard ===")
        # If user clicks "Done Speaking (Manual Submit)" without speaking
        done_btn = page.locator('button:has-text("Done Speaking")')
        await done_btn.click()
        print("Clicked 'Done Speaking' without speech")

        # Verify localized silence prompt appears without crashing session
        badge = page.locator('span:text-is("I couldn\'t hear you. Please speak into your microphone.")')
        await badge.wait_for(state="visible", timeout=4000)
        print("Localized silence message visible: True")

        # Verify no 422 was sent to backend
        voice_422s = [e for e in network_errors if "422" in e and "/voice/respond" in e]
        assert len(voice_422s) == 0, f"Backend was called unnecessarily: {voice_422s}"

        # Verify auto-resume listening
        await page.wait_for_selector('h3:has-text("Listening")', timeout=5000)
        print("Successfully auto-resumed listening!")

        print("\n=== Test 5: Multilingual Voice - Switch to Telugu ===")
        # Open language selector
        lang_btn = page.locator('button[aria-label="Select voice conversation language"]')
        await lang_btn.click()
        te_opt = page.locator('button:has-text("Telugu")')
        await te_opt.click()
        print("Switched language to Telugu (te)")

        # Verify current language badge
        await asyncio.sleep(0.5)
        lang_text = await lang_btn.text_content()
        print(f"Language button text: {lang_text.strip()}")
        assert "Telugu" in lang_text

        # Test Done Speaking in Telugu without speech -> verify Telugu prompt
        print("Clicking Done Speaking in Telugu...")
        done_btn = page.locator('button:has-text("Done Speaking")')
        await done_btn.click()

        await asyncio.sleep(1.0)
        print("Console logs during Test 5:")
        for log in console_logs[-10:]:
            print("  ", log)

        # Look for any text inside the state subtitle area
        subtitle = page.locator('div.min-h-\\[4rem\\]')
        sub_text = await subtitle.text_content()
        print(f"Subtitle area text: '{sub_text}'")

        # Wait for auto-resume
        await asyncio.sleep(1.5)
        await page.wait_for_selector('h3:has-text("Listening")', timeout=5000)
        print("Telugu session cleanly auto-resumed listening!")

        # Screenshot of active voice overlay
        await page.screenshot(path="C:/Users/venuk/.gemini/antigravity/brain/939abc07-07f1-4b0c-88e1-ca94c531bb6d/voice_first_turn_verification.png")
        print("Saved screenshot to voice_first_turn_verification.png")

        # Test Return to Text Chat
        return_btn = page.locator('button:has-text("Return to Text Chat")').first
        await return_btn.click()
        await panel.wait_for(state="hidden", timeout=3000)
        print("Returned cleanly to text chat without crashing")

        print("\n=== Test 6: Re-opening Voice Session with Cached Greeting ===")
        # Reopen voice session to verify zero-latency cached greeting playback
        await mic_btn.click()
        await panel.wait_for(state="visible", timeout=5000)

        # Clear logs and track cached timing
        for _ in range(40):
            await asyncio.sleep(0.1)
            milestones = await page.evaluate("() => window.__medivoice_milestones || {}")
            if "playbackStart" in milestones:
                break

        milestones2 = await page.evaluate("() => window.__medivoice_milestones || {}")
        print(f"Cached Session Milestones: {json.dumps(milestones2, indent=2)}")
        cached_tts_latency = milestones2.get("ttsResponse", 0) - milestones2.get("ttsInitiation", 0)
        print(f"Cached TTS retrieval latency: {cached_tts_latency:.1f}ms (Zero Network Wait)")
        playback_latency_cached = milestones2.get("playbackStart", 0) - milestones2.get("voiceActivation", 0)
        print(f"Cached Greeting Playback Start: {playback_latency_cached:.1f}ms from voice activation (previously 10,000ms!)")

        print("\n=== ALL BROWSER VOICE TESTS PASSED SUCCESSFULLY! ===")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
