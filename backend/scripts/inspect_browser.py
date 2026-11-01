import os, time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        channel="msedge",
        headless=True,
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ],
    )
    context = browser.new_context(permissions=["microphone"])
    page = context.new_page()

    page.goto("http://localhost:3000/")
    time.sleep(2)
    page.screenshot(path="backend/scripts/home_page.png")
    print("Home page screenshot captured")

    # Click voice button
    btn = page.locator("button:has-text('Talk to MediVoice')").first
    if btn.is_visible():
        btn.click()
        print("Clicked Talk to MediVoice")
        time.sleep(3)
        page.screenshot(path="backend/scripts/voice_active.png")
        print("Voice active screenshot captured")
        print("Visible buttons:", [b.inner_text() for b in page.locator("button").all() if b.is_visible()])
    else:
        print("Talk to MediVoice button not visible")
    browser.close()

