#!/usr/bin/env python3
"""
知乎内容爬取脚本 - 从已登录的浏览器中获取内容
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    auth_file = "data/zhihu_auth.json"

    print("=" * 60)
    print("知乎内容爬取工具")
    print("=" * 60)
    print("\n请在浏览器中执行以下操作:")
    print("  1. 登录知乎")
    print("  2. 访问: https://www.zhihu.com/people/aote-zhi-fu")
    print("  3. 点击\"回答\"标签")
    print("  4. 滚动页面加载更多回答")
    print("  5. 完成后回到终端按回车")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )

        context_options = {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "viewport": {"width": 1920, "height": 1080},
        }

        if os.path.exists(auth_file):
            context_options["storage_state"] = auth_file

        context = await browser.new_context(**context_options)
        page = await context.new_page()

        # 访问知乎
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        print("\n浏览器已打开")
        print("请在浏览器中操作，完成后回到终端按回车继续...")
        print("（如果想退出，请直接关闭浏览器）")

        # 等待用户输入，不要按回车就继续
        try:
            input("\n按回车继续提取数据...")
        except EOFError:
            print("\n检测到浏览器已关闭，尝试提取数据...")

        # 检查浏览器是否还开着
        try:
            current_url = page.url
            print(f"当前URL: {current_url}")
        except Exception as e:
            print(f"浏览器已关闭: {e}")
            await browser.close()
            print("\n请重新运行脚本，并在按回车前保持浏览器打开")
            return

        # 获取数据
        print("\n正在提取数据...")

        try:
            answers = await page.evaluate("""() => {
                const results = [];
                const items = document.querySelectorAll('.List-item, .ContentItem');

                items.forEach(item => {
                    try {
                        const titleEl = item.querySelector('.ContentItem-title a, .question-link, a[title]');
                        const title = titleEl ? titleEl.innerText.trim() : '';
                        const titleHref = titleEl ? titleEl.href : '';
                        const contentEl = item.querySelector('.RichText, .content, [itemprop="text"]');
                        const content = contentEl ? contentEl.innerText.trim() : '';
                        const voteEl = item.querySelector('.VoteButton, [class*="vote"]');
                        const voteText = voteEl ? voteEl.innerText.trim() : '0';
                        const voteCount = parseInt(voteText.replace(/[^0-9]/g, '')) || 0;
                        const answerLink = item.querySelector('a[href*="/answer/"]');
                        const answerUrl = answerLink ? answerLink.href : '';

                        if (title || content) {
                            results.push({
                                question_title: title,
                                question_url: titleHref,
                                answer_url: answerUrl,
                                content: content,
                                vote_count: voteCount
                            });
                        }
                    } catch (e) {}
                });

                return results;
            }""")
        except Exception as e:
            print(f"提取数据失败: {e}")
            await browser.close()
            return

        print(f"\n提取到 {len(answers)} 条回答:")
        for i, ans in enumerate(answers[:5], 1):
            print(f"  {i}. {ans['question_title'][:50]}...")

        # 保存数据
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "奥特之父_answers_from_browser.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 数据已保存到: {output_file}")

        print("\n请关闭浏览器")
        await browser.close()

    print("\n完成!")


if __name__ == "__main__":
    asyncio.run(main())