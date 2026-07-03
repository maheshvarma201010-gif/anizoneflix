import asyncio
from playwright.async_api import async_playwright

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Define viewports
        viewports = [
            {"name": "mobile", "width": 375, "height": 667},
            {"name": "tablet", "width": 768, "height": 1024},
            {"name": "desktop", "width": 1280, "height": 800}
        ]

        for vp in viewports:
            context = await browser.new_context(viewport={"width": vp["width"], "height": vp["height"]})
            page = await context.new_page()

            # Navigate to homepage
            print(f"Verifying {vp['name']} layout...")
            await page.goto("http://localhost:10000")
            await page.wait_for_timeout(2000)  # Wait for animations and Swiper

            # Take screenshot
            await page.screenshot(path=f"verification/{vp['name']}.png", full_page=True)

            # Check grid on mobile
            if vp["name"] == "mobile":
                # Check if trendingSwiper is present and has slides
                slides_count = await page.evaluate("document.querySelectorAll('.trendingSwiper .swiper-slide').length")
                print(f"Mobile slides count: {slides_count}")

                # Verify that swiper is initialized with slidesPerView 2 (approximately)
                # We can check the width of a slide relative to the container
                slide_width = await page.evaluate("document.querySelector('.trendingSwiper .swiper-slide').offsetWidth")
                container_width = await page.evaluate("document.querySelector('.trendingSwiper').offsetWidth")
                print(f"Slide width: {slide_width}, Container width: {container_width}")
                if slide_width > 0 and slide_width < container_width:
                     print(f"Ratio: {container_width / slide_width}")

            await context.close()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify())
