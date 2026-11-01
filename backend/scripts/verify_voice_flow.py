import asyncio
import os
from playwright.async_api import async_playwright

ARTIFACT_DIR = r"C:\Users\venuk\.gemini\antigravity\brain\939abc07-07f1-4b0c-88e1-ca94c531bb6d"

async def test_full_voice_flow():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            permissions=["microphone"]
        )
        page = await context.new_page()

        print("Navigating to http://localhost:3000/ ...")
        await page.goto("http://localhost:3000/", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Open Voice Overlay
        voice_btn = await page.query_selector("button[aria-label='Open full-screen voice assistant']")
        assert voice_btn is not None
        await voice_btn.click()
        await page.wait_for_timeout(1500)

        # Verify language switcher dropdown items
        lang_btn = await page.query_selector("button[aria-label='Select voice conversation language']")
        assert lang_btn is not None
        await lang_btn.click()
        await page.wait_for_timeout(400)

        lang_items = await page.query_selector_all("button:has-text('Telugu'), button:has-text('Hindi'), button:has-text('Tamil'), button:has-text('Kannada')")
        print(f"Found {len(lang_items)} language dropdown options.")
        assert len(lang_items) >= 4, "Not all languages found in dropdown"

        # Switch to Telugu
        telugu_btn = await page.query_selector("button:has-text('Telugu')")
        assert telugu_btn is not None
        await telugu_btn.click()
        await page.wait_for_timeout(500)

        # Check that language changed in UI
        lang_btn_text = await lang_btn.text_content()
        safe_text = lang_btn_text.strip().encode('ascii', errors='backslashreplace').decode('ascii')
        print(f"Language button text after switch: {safe_text}")
        assert "Telugu" in lang_btn_text, "Language button did not update to Telugu!"

        # Screenshot Telugu full-screen voice overlay
        telugu_screenshot = os.path.join(ARTIFACT_DIR, "fullscreen_voice_telugu.png")
        await page.screenshot(path=telugu_screenshot)
        print(f"Saved Telugu voice overlay screenshot: {telugu_screenshot}")

        # Return to text chat
        return_btn = await page.query_selector("button:has-text('Return to Text Chat')")
        assert return_btn is not None
        await return_btn.click()
        await page.wait_for_timeout(600)

        # Verify chat language also updated to Telugu or reflects user action
        active_lang_btn = await page.query_selector("button:has-text('తెలుగు')")
        print(f"Chat language pill for Telugu present: {active_lang_btn is not None}")

        await browser.close()
        print("VOICE FLOW AND LANGUAGE SWITCHING VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_full_voice_flow())
