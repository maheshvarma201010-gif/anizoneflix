import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        try:
            # Increase timeout and handle potential errors
            await page.goto("http://localhost:10000", timeout=60000)
            await page.wait_for_timeout(2000) # Wait for animations
            await page.screenshot(path="home_verify.png", full_page=True)
            print("Screenshot saved to home_verify.png")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
