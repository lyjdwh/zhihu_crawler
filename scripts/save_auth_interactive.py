#!/usr/bin/env python3
"""
知乎登录认证保存脚本
运行此脚本，在浏览器中登录知乎，然后按回车保存认证状态
"""

import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    auth_file = "data/zhihu_auth.json"

    print("=" * 60)
    print("知乎登录认证保存工具")
    print("=" * 60)
    print("\n此脚本将打开浏览器让您登录知乎")
    print("登录完成后，脚本会自动保存认证状态\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        page = await context.new_page()

        # 访问知乎登录页
        await page.goto("https://www.zhihu.com/signin")
        print("请在浏览器中登录知乎...")
        print("登录完成后，在浏览器中访问 https://www.zhihu.com 确认登录成功")
        print("\n然后回到此终端按回车键继续...")

        # 等待用户按回车
        input()

        # 验证是否登录成功
        await page.goto("https://www.zhihu.com")
        await asyncio.sleep(2)

        is_logged_in = await page.evaluate("""() => {
            return !!document.querySelector('.AppHeader-avatar') ||
                   !!document.querySelector('[class*="avatar"]') ||
                   !document.querySelector('.AppHeader-login');
        }""")

        if is_logged_in:
            # 保存认证状态
            await context.storage_state(path=auth_file)
            print(f"\n✓ 登录成功！认证已保存到: {auth_file}")
        else:
            print("\n✗ 登录失败，请重新运行此脚本")

        await browser.close()

    print("\n现在您可以运行爬取内容的脚本了。")


if __name__ == "__main__":
    asyncio.run(main())