"""All browser automation uses installed Google Chrome, with isolated contexts."""
from __future__ import annotations


async def launch_chrome(playwright, *, headless: bool, slow_mo: int = 0):
    return await playwright.chromium.launch(channel="chrome", headless=headless, slow_mo=slow_mo)


async def check_chrome():
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await launch_chrome(playwright, headless=True)
        try:
            return browser.version
        finally:
            await browser.close()


if __name__ == "__main__":
    import asyncio
    print("Google Chrome " + asyncio.run(check_chrome()))
