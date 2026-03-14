#!/usr/bin/env python3
"""
直接爬取方案 - 使用浏览器模拟滚动
绕过 API 限制，直接从页面获取数据
"""
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# 配置
OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

USER_URL = "https://www.zhihu.com/people/xu-ze-qiu/answers"
BATCH_SIZE = 50


async def scroll_and_collect(page, expected_count=4832):
    """滚动页面并收集数据"""
    answers = []
    last_count = 0
    no_change_count = 0
    max_no_change = 5
    scroll_count = 0

    print(f"开始滚动收集数据，目标: {expected_count} 条回答")
    print("="*60)

    while len(answers) < expected_count:
        scroll_count += 1

        # 滚动页面
        await page.evaluate("""() => {
            window.scrollTo(0, document.body.scrollHeight);
        }""")
        await asyncio.sleep(2)  # 等待内容加载

        # 提取页面上的回答数据
        current_answers = await page.evaluate("""() => {
            const items = document.querySelectorAll('[data-zop]');
            const data = [];
            items.forEach(item => {
                try {
                    const zop = JSON.parse(item.getAttribute('data-zop') || '{}');
                    if (zop.type === 'Answer') {
                        // 获取问题和回答内容
                        const questionLink = item.querySelector('a[href*="/question/"]');
                        const contentDiv = item.querySelector('.RichContent-inner');
                        const voteBtn = item.querySelector('[data-zop-reaction-button]');

                        data.push({
                            id: zop.itemId,
                            type: 'answer',
                            question: {
                                id: zop.rootItemId,
                                title: zop.title || (questionLink ? questionLink.textContent.trim() : '')
                            },
                            content: contentDiv ? contentDiv.innerHTML : '',
                            url: `https://www.zhihu.com/question/${zop.rootItemId}/answer/${zop.itemId}`
                        });
                    }
                } catch (e) {}
            });
            return data;
        }""")

        # 合并新数据
        for ans in current_answers:
            if not any(a['id'] == ans['id'] for a in answers):
                answers.append(ans)

        # 检查是否有变化
        if len(answers) == last_count:
            no_change_count += 1
            if no_change_count >= max_no_change:
                print(f"\n连续 {max_no_change} 次滚动无新数据，结束收集")
                break
        else:
            no_change_count = 0

        last_count = len(answers)

        # 显示进度
        if scroll_count % 5 == 0 or len(answers) % 50 == 0:
            progress = (len(answers) / expected_count) * 100 if expected_count > 0 else 0
            print(f"  滚动 {scroll_count:3d} 次 | 已收集: {len(answers):4d} 条 | 进度: {progress:.1f}%")

        # 定期保存
        if len(answers) % BATCH_SIZE == 0 and len(answers) > 0:
            await save_batch(answers, len(answers) // BATCH_SIZE)

    print("="*60)
    print(f"收集完成: 共 {len(answers)} 条回答")

    return answers


async def save_batch(answers, batch_index):
    """保存批次数据"""
    filename = OUTPUT_DIR / f"奥特之父_answers_batch_{batch_index}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)
    print(f"  已保存批次 #{batch_index}: {len(answers)} 条")


async def main():
    print("="*60)
    print("知乎数据爬取工具 - 奥特之父直接爬取版")
    print("="*60)
    print(f"输出目录: {OUTPUT_DIR}")
    print("="*60)

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security"
            ]
        )

        # 创建上下文
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        # 隐藏自动化特征
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        """)

        # 创建页面
        page = await context.new_page()

        try:
            # 访问用户回答页面
            print(f"\n正在访问: {USER_URL}")
            await page.goto(USER_URL, wait_until="domcontentloaded")
            await asyncio.sleep(5)  # 等待页面加载

            print("页面已加载，开始收集数据...\n")

            # 滚动并收集数据
            answers = await scroll_and_collect(page, expected_count=4832)

            # 保存最终批次
            if answers:
                batch_count = (len(answers) + BATCH_SIZE - 1) // BATCH_SIZE
                for i in range(batch_count):
                    start = i * BATCH_SIZE
                    end = min(start + BATCH_SIZE, len(answers))
                    await save_batch(answers[start:end], i)

                print(f"\n{'='*60}")
                print(f"✅ 爬取完成!")
                print(f"{'='*60}")
                print(f"  - 总计: {len(answers)} 条回答")
                print(f"  - 批次: {batch_count} 个文件")
                print(f"  - 目录: {OUTPUT_DIR}")
                print(f"{'='*60}")

        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()
            print("\n浏览器已关闭")


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断，程序已退出")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
