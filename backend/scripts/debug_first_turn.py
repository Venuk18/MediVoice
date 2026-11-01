import asyncio
import os
import json
from playwright.async_api import async_playwright

async def debug_voice():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            permissions=["microphone"]
        )
        page = await context.new_page()

        page.on("console", lambda msg: print(f"[CONSOLE {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}"))

        def handle_request(req):
            if "voice" in req.url:
                print(f"[REQ] {req.method} {req.url}")
        page.on("request", handle_request)

        async def handle_response(res):
            if "voice" in res.url:
                body = ""
                try:
                    if "respond" in res.url:
                        body = await res.text()
                except Exception:
                    pass
                print(f"[RES] {res.status} {res.url} | body={body[:150]}")
        page.on("response", handle_response)

        print("Navigating to http://localhost:3000/ ...")
        t0 = asyncio.get_event_loop().time()
        await page.goto("http://localhost:3000/", wait_until="networkidle")
        print(f"Page loaded in {asyncio.get_event_loop().time()-t0:.2f}s")

        # Click Voice AI button
        voice_btn = await page.query_selector("button[aria-label='Open full-screen voice assistant']")
        assert voice_btn is not None
        print(f"[{asyncio.get_event_loop().time()-t0:.2f}s] Clicking Voice AI button...")
        t_click = asyncio.get_event_loop().time()
        await voice_btn.click()

        # Monitor what happens over the next 15 seconds
        for i in range(15):
            await page.wait_for_timeout(1000)
            now = asyncio.get_event_loop().time()
            # Check voice state in DOM
            state_text = await page.evaluate("() => { const h3 = document.querySelector('h3'); return h3 ? h3.innerText : 'none'; }")
            print(f"[{now-t_click:.1f}s] Current State: {state_text}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_voice())
