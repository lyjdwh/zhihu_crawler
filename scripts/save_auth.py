#!/usr/bin/env python3
"""
知乎登录凭证保存脚本

使用方法:
    python scripts/save_auth.py

功能:
    - 打开浏览器访问知乎
    - 等待用户手动登录
    - 自动保存登录凭证到 data/zhihu_auth.json
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from playwright.async_api import async_playwright
from core.config import ZHIHU_CONFIG


async def save_auth():
    """保存知乎登录凭证"""
    print("\n" + "=" * 60)
    print("知乎登录凭证保存工具")
    print("=" * 60 + "\n")

    print("正在启动浏览器...")

    async with async_playwright() as p:
        # 启动浏览器（非无头模式，方便用户操作）
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        # 创建新上下文
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        # 创建页面
        page = await context.new_page()

        # 访问知乎登录页
        print("\n请在浏览器中登录知乎...")
        print("登录成功后，脚本会自动保存凭证\n")

        await page.goto("https://www.zhihu.com/signin")

        # 等待用户登录
        max_attempts = 60  # 最多等待5分钟
        for attempt in range(max_attempts):
            await asyncio.sleep(5)

            # 检查是否已登录
            is_logged_in = await page.evaluate("""() => {
                const avatar = document.querySelector('.Avatar, .AppHeader-profile');
                const username = document.querySelector('.ProfileHeader-name, .UserLink-link');
                return !!(avatar || username);
            }""")

            if is_logged_in:
                print(f"\n✓ 检测到登录成功！")
                break

            print(f"等待登录... ({attempt + 1}/{max_attempts})")

        else:
            print("\n✗ 等待超时，未检测到登录状态")
            await browser.close()
            return False

        # 保存登录凭证
        auth_file = ZHIHU_CONFIG["auth_file"]
        auth_file.parent.mkdir(parents=True, exist_ok=True)

        await context.storage_state(path=str(auth_file))

        print(f"\n✓ 登录凭证已保存到: {auth_file}")

        # 验证保存成功
        if auth_file.exists():
            import json
            with open(auth_file, 'r', encoding='utf-8') as f:
                auth_data = json.load(f)
                cookies = auth_data.get('cookies', [])
                print(f"  - 保存了 {len(cookies)} 个 cookies")

        await browser.close()
        return True


async def main():
    """主函数"""
    try:
        success = await save_auth()
        if success:
            print("\n" + "=" * 60)
            print("登录凭证保存成功！")
            print("=" * 60)
            print("\n现在可以运行爬取脚本：")
            print("  python scripts/crawl_aote.py")
        else:
            print("\n✗ 保存失败")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n用户取消操作")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
