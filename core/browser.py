"""
浏览器管理模块 - 统一处理 Playwright 初始化和反爬措施
"""

import asyncio
import os
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)


class BrowserManager:
    """浏览器管理器"""

    DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(
        self,
        auth_file: str = "data/zhihu_auth.json",
        headless: bool = False,
        user_agent: Optional[str] = None,
        timeout: int = 60000,
    ):
        self.auth_file = auth_file
        self.headless = headless
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def init(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        context_options = {
            "user_agent": self.user_agent,
            "viewport": {"width": 1920, "height": 1080},
        }

        auth_path = os.path.abspath(self.auth_file)
        if os.path.exists(auth_path):
            context_options["storage_state"] = auth_path

        self.context = await self.browser.new_context(**context_options)

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.timeout)

        await self.page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)

    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def wait_for_load(self, delay: float = 3.0):
        """等待页面加载"""
        await asyncio.sleep(delay)

    async def scroll_and_wait(self, distance: int = 1200, delay: float = 2.0):
        """滚动并等待"""
        await self.page.evaluate(f"window.scrollBy(0, {distance});")
        await asyncio.sleep(delay)
