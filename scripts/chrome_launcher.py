"""
Google Chrome 生命周期管理。

Usage:
    python scripts/chrome_launcher.py               # 启动 Google Chrome
    python scripts/chrome_launcher.py --headless     # 无头模式
"""
from __future__ import annotations

import argparse
import asyncio
from dy_cli.utils.browser import launch_chrome


async def launch_chromium(headless: bool = False):
    """使用 Playwright 启动隔离的 Google Chrome。"""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await launch_chrome(pw, headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded")

        print(f"[dy] Google Chrome 已启动")
        print(f"[dy] Headless: {headless}")
        print(f"[dy] 按 Ctrl+C 关闭")

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await browser.close()
            print("[dy] Google Chrome 已关闭")


def kill_chromium():
    # Never kill the user's unrelated Chrome windows.
    raise SystemExit("请在启动终端按 Ctrl+C，仅关闭本次 Chrome；--kill 不再全局终止浏览器。")


def main():
    parser = argparse.ArgumentParser(description="Google Chrome 管理")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--kill", action="store_true", help="已停用：请在启动终端按 Ctrl+C")
    args = parser.parse_args()

    if args.kill:
        kill_chromium()
    else:
        asyncio.run(launch_chromium(headless=args.headless))


if __name__ == "__main__":
    main()
