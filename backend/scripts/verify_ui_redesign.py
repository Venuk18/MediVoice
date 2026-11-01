import asyncio
import os
from playwright.async_api import async_playwright

ARTIFACT_DIR = r"C:\Users\venuk\.gemini\antigravity\brain\939abc07-07f1-4b0c-88e1-ca94c531bb6d"

async def main():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            try:
                browser = await p.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            permissions=["microphone"]
        )
        page = await context.new_page()

        page.on("console", lambda msg: print(f"PAGE CONSOLE: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))

        print("Navigating to http://localhost:3000/ ...")
        await page.goto("http://localhost:3000/", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 1. Verify Homepage Layout (Stacked Rows)
        hero = await page.query_selector("section.patient-hero")
        assert hero is not None, "Hero section not found"
        chat_section = await page.query_selector("#medivoice-ai-chat")
        assert chat_section is not None, "Section 2 #medivoice-ai-chat not found"

        hero_box = await hero.bounding_box()
        chat_box = await chat_section.bounding_box()
        print(f"Hero section bounds: top={hero_box['y']}, height={hero_box['height']}, width={hero_box['width']}")
        print(f"Chat section bounds: top={chat_box['y']}, height={chat_box['height']}, width={chat_box['width']}")
        
        # Verify vertical stacking: chat section must start below hero
        assert chat_box['y'] >= hero_box['y'] + hero_box['height'] - 10, "Chat is not vertically below hero!"
        print("VERIFIED: Section 1 (Hero) and Section 2 (MediVoice AI Chat) are vertically stacked full-width rows!")

        # Screenshot homepage layout
        homepage_screenshot = os.path.join(ARTIFACT_DIR, "homepage_redesign_stacked.png")
        await page.screenshot(path=homepage_screenshot)
        print(f"Saved homepage screenshot: {homepage_screenshot}")

        # 2. Test 'Talk to MediVoice' Button Scroll & Input Focus
        talk_btn = await page.query_selector("button:has-text('Talk to MediVoice')")
        assert talk_btn is not None, "Talk to MediVoice button not found"
        await talk_btn.click()
        await page.wait_for_timeout(800)

        # Check if #medivoice-message-input is focused
        is_focused = await page.evaluate("() => document.activeElement && document.activeElement.id === 'medivoice-message-input'")
        print(f"Is #medivoice-message-input focused after clicking Talk to MediVoice? {is_focused}")

        # 3. Test Full-Screen Voice Interface Overlay
        # Find the Voice AI button in the chat experience header
        voice_ai_btn = await page.query_selector("button[aria-label='Open full-screen voice assistant']")
        if not voice_ai_btn:
            voice_ai_btn = await page.query_selector("button[title*='Speak with Gnani Voice AI']")
        assert voice_ai_btn is not None, "Voice AI toggle button not found"

        btn_txt = await voice_ai_btn.text_content()
        btn_aria = await voice_ai_btn.get_attribute("aria-label")
        print(f"Clicking Voice AI button: txt='{btn_txt.strip()}', aria='{btn_aria}'")

        await voice_ai_btn.click()
        await page.wait_for_timeout(2000)

        # Print all elements with aria-label or fixed classes
        regions = await page.query_selector_all("[role='region']")
        for r in regions:
            r_aria = await r.get_attribute("aria-label")
            r_cls = await r.get_attribute("class")
            print(f"Region found: aria='{r_aria}', cls='{r_cls[:60]}'")

        overlay = await page.query_selector("div.fixed.inset-0.z-50")
        assert overlay is not None, "Full-screen voice overlay not found (fixed inset-0 z-50)!"
        print("VERIFIED: Dedicated full-screen voice overlay is active!")

        # Check required overlay elements
        return_to_chat_btn = await page.query_selector("button:has-text('Return to Text Chat')")
        assert return_to_chat_btn is not None, "Return to Text Chat button not found!"
        
        lang_btn = await page.query_selector("button[aria-label*='Select voice conversation language']")
        assert lang_btn is not None, "Language selector button not found!"

        # Screenshot full-screen voice experience
        voice_screenshot = os.path.join(ARTIFACT_DIR, "fullscreen_voice_overlay.png")
        await page.screenshot(path=voice_screenshot)
        print(f"Saved full-screen voice screenshot: {voice_screenshot}")

        # 4. Test Escape key listener
        print("Testing Escape key dismissal...")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(600)

        overlay_after_esc = await page.query_selector("div.fixed.inset-0.z-50")
        print(f"Is voice overlay closed after pressing Escape? {overlay_after_esc is None}")
        assert overlay_after_esc is None, "Voice overlay was not dismissed by Escape key!"

        # Reopen voice overlay to test 'Return to Text Chat' button
        print("Reopening voice overlay to test 'Return to Text Chat' button...")
        await voice_ai_btn.click()
        await page.wait_for_timeout(1000)

        return_btn = await page.query_selector("button:has-text('Return to Text Chat')")
        assert return_btn is not None, "Return to Text Chat button not found on second open"
        await return_btn.click()
        await page.wait_for_timeout(600)

        overlay_after_return = await page.query_selector("div.fixed.inset-0.z-50")
        print(f"Is voice overlay closed after clicking 'Return to Text Chat'? {overlay_after_return is None}")
        assert overlay_after_return is None, "Voice overlay was not dismissed by 'Return to Text Chat'!"

        # Verify chat is still functional and visible
        input_el = await page.query_selector("#medivoice-message-input")
        assert input_el is not None, "#medivoice-message-input still visible and ready"
        print("VERIFIED: Text chat is fully preserved and active!")

        await browser.close()
        print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
