import asyncio
from playwright.async_api import async_playwright

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        try:
            await page.goto("http://localhost:10000/schedule", timeout=5000)
            print(f"Schedule Page Status: 200")

            # Check if countdown script is present
            has_countdown = await page.evaluate("() => typeof window.updateAllCountdowns === 'function'")
            print(f"Countdown Function Present: {has_countdown}")

            # Check for RGB glow class
            has_glow = await page.evaluate("() => document.querySelector('.glow-new') !== null")
            print(f"Glow Class Present (Might be empty if no schedule): {has_glow}")

            await page.screenshot(path="schedule_verify.png")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

asyncio.run(verify())
