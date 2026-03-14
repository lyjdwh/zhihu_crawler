#!/usr/bin/env python3
"""调试脚本 - 检查知乎用户页面结构"""

import asyncio
import os
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


async def main():
    auth_file = "data/zhihu_auth.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        context_options = {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
        }

        auth_path = os.path.abspath(auth_file)
        if os.path.exists(auth_path):
            context_options["storage_state"] = auth_path

        context = await browser.new_context(**context_options)
        page = await context.new_page()

        # 访问知乎用户主页
        user_url = "https://www.zhihu.com/people/aote-zhi-fu"
        print(f"访问: {user_url}")
        await page.goto(user_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 打印页面标题
        print(f"\n页面标题: {await page.title()}")
        print(f"当前URL: {page.url}")

        # 尝试获取用户名
        name = await page.evaluate("""() => {
            const selectors = [
                '.ProfileHeader-name',
                '.name',
                '.AppHeader-title',
                '.ProfileMain-headerInfo .name',
                'h1',
                '.author-name'
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) return sel + ': ' + el.innerText.trim();
            }
            return '未找到用户名';
        }""")
        print(f"\n用户名: {name}")

        # 获取关键元素信息
        elements = await page.evaluate("""() => {
            const result = {
                list_items: document.querySelectorAll('.List-item').length,
                content_items: document.querySelectorAll('.ContentItem').length,
                question_links: document.querySelectorAll('a[href*="/question/"]').length,
                profile_main: !!document.querySelector('.ProfileMain'),
                tabs: document.querySelectorAll('.Tabs-tab').length
            };

            // 尝试获取回答tab的链接
            const answerTab = document.querySelector('a[href*="/answers"]');
            if (answerTab) {
                result.answers_tab = answerTab.href;
            }

            return result;
        }""")
        print(f"\n元素信息: {json.dumps(elements, indent=2)}")

        input("\n按回车键退出...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())