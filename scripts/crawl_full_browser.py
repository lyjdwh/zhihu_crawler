#!/usr/bin/env python3
"""
完全浏览器模拟爬取方案
使用真实的浏览器行为来避免反爬检测
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def save_batch(answers, batch_index):
    """保存批次数据"""
    filename = OUTPUT_DIR / f"奥特之父_answers_batch_{batch_index}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)
    print(f"  [保存] 批次 #{batch_index}: {len(answers)} 条")


async def main():
    print("="*60)
    print("知乎数据爬取 - 完全浏览器模拟")
    print("="*60)

    async with async_playwright() as p:
        # 启动浏览器 - 不使用无头模式
        print("\n启动浏览器...")
        browser = await p.chromium.launch(
            headless=False,  # 不使用无头模式，更像真实用户
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )

        # 创建新上下文（不使用存储状态）
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )

        page = await context.new_page()

        try:
            # 访问首页
            print("访问知乎首页...")
            await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 检查是否需要登录
            login_btn = await page.query_selector('[data-za-detail-view-element_name="Login"]')
            if login_btn:
                print("需要登录，请先手动登录...")
                # 等待用户手动登录
                print("请在浏览器中登录知乎（你有60秒时间）...")
                await asyncio.sleep(60)

            # 访问用户回答页面
            print("\n访问奥特之父回答页面...")
            await page.goto("https://www.zhihu.com/people/xu-ze-qiu/answers", wait_until="domcontentloaded")
            await asyncio.sleep(5)

            print("开始滚动收集数据...")
            all_answers = []
            seen_ids = set()
            scroll_count = 0
            last_count = 0
            no_change = 0

            while len(all_answers) < 4832:
                scroll_count += 1

                # 滚动到底部
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(2.5)

                # 提取数据
                items = await page.query_selector_all('.ContentItem.AnswerItem, [data-zop*="Answer"]')

                current_batch = []
                for item in items:
                    try:
                        # 获取回答ID
                        item_id = await item.get_attribute('name') or await item.get_attribute('data-za-content-id')
                        if not item_id:
                            continue

                        if item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)

                        # 获取问题标题
                        q_title = await item.query_selector('h2.ContentItem-title a')
                        question_title = await q_title.inner_text() if q_title else ""

                        current_batch.append({
                            'id': item_id,
                            'question_title': question_title
                        })
                    except:
                        pass

                all_answers.extend(current_batch)

                # 检查进度
                if scroll_count % 5 == 0:
                    print(f"  滚动 {scroll_count} 次，已收集 {len(all_answers)} 条")

                # 检查是否还有新数据
                if len(all_answers) == last_count:
                    no_change += 1
                    if no_change >= 5:
                        print("连续多次无新数据，结束收集")
                        break
                else:
                    no_change = 0

                last_count = len(all_answers)

            print(f"\n收集完成，共 {len(all_answers)} 条")

            # 保存数据
            if all_answers:
                save_batch(all_answers, 0)
                print(f"数据已保存到 {OUTPUT_DIR}")

        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()
            print("浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序被中断")
