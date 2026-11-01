import asyncio
import os
from playwright.async_api import async_playwright

ARTIFACT_DIR = r"C:\Users\venuk\.gemini\antigravity\brain\939abc07-07f1-4b0c-88e1-ca94c531bb6d"

async def test_viewports():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        for vp_name, w, h in [("mobile", 375, 667), ("tablet", 768, 1024)]:
            context = await browser.new_context(viewport={"width": w, "height": h}, permissions=["microphone"])
            page = await context.new_page()

            await page.goto("http://localhost:3000/", wait_until="networkidle")
            await page.wait_for_timeout(1000)

            # Screenshot homepage in this viewport
            hp_path = os.path.join(ARTIFACT_DIR, f"homepage_{vp_name}.png")
            await page.screenshot(path=hp_path)
            print(f"Saved {vp_name} homepage screenshot: {hp_path}")

            # Open voice overlay
            voice_btn = await page.query_selector("button[aria-label='Open full-screen voice assistant'], button[title*='Speak with Gnani Voice AI']")
            assert voice_btn is not None
            await voice_btn.click()
            await page.wait_for_timeout(1000)

            # Screenshot voice overlay in this viewport
            voice_path = os.path.join(ARTIFACT_DIR, f"voice_overlay_{vp_name}.png")
            await page.screenshot(path=voice_path)
            print(f"Saved {vp_name} voice overlay screenshot: {voice_path}")

            await context.close()

        await browser.close()
        print("RESPONSIVE VIEWPORT TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(test_viewports())

