#!/usr/bin/env python3
"""
JavaScript注入爬取方案
通过分析知乎页面中的初始数据和GraphQL接口获取回答
"""
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def save_batch(answers, batch_index):
    """保存批次数据"""
    if not answers:
        return
    filename = OUTPUT_DIR / f"奥特之父_answers_batch_{batch_index}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)
    print(f"  [保存] 批次 #{batch_index}: {len(answers)} 条 -> {filename.name}")


async def extract_from_page(page):
    """从页面提取回答数据"""
    # 等待页面加载完成
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)

    # 尝试从 window 对象获取初始数据
    initial_data = await page.evaluate("""() => {
        // 尝试多种可能的数据来源
        const data = {
            initialState: window.initialState,
            __INITIAL_STATE__: window.__INITIAL_STATE__,
            __data: window.__data,
            _SSR_HYDRATED_DATA: window._SSR_HYDRATED_DATA
        };
        return data;
    }""")

    answers = []

    # 处理 initialState
    if initial_data.get('initialState'):
        try:
            state = initial_data['initialState']
            if isinstance(state, str):
                state = json.loads(state)

            # 查找 answers 数据
            if 'entities' in state and 'answers' in state['entities']:
                answers_data = state['entities']['answers']
                for ans_id, ans_data in answers_data.items():
                    if 'question' in ans_data:
                        answers.append({
                            'id': str(ans_id),
                            'type': 'answer',
                            'question': {
                                'id': str(ans_data['question'].get('id', '')),
                                'title': ans_data['question'].get('title', '')
                            },
                            'content': ans_data.get('content', ''),
                            'voteup_count': ans_data.get('voteup_count', 0),
                            'comment_count': ans_data.get('comment_count', 0),
                            'created_time': ans_data.get('created_time', 0),
                            'url': f"https://www.zhihu.com/question/{ans_data['question'].get('id', '')}/answer/{ans_id}"
                        })
        except Exception as e:
            print(f"解析 initialState 失败: {e}")

    # 如果 initialState 没有数据，尝试从 DOM 提取
    if not answers:
        print("从 DOM 提取数据...")
        dom_data = await page.evaluate("""() => {
            const items = document.querySelectorAll('.ContentItem.AnswerItem, [data-zop*=\"Answer\"]');
            const data = [];
            items.forEach(item => {
                const zop = item.getAttribute('data-zop');
                if (zop) {
                    try {
                        const parsed = JSON.parse(zop);
                        data.push({
                            id: parsed.itemId,
                            questionId: parsed.rootItemId,
                            title: parsed.title
                        });
                    } catch(e) {}
                }
            });
            return data;
        }""")

        for item in dom_data:
            answers.append({
                'id': str(item['id']),
                'type': 'answer',
                'question': {
                    'id': str(item['questionId']),
                    'title': item.get('title', '')
                },
                'url': f"https://www.zhihu.com/question/{item['questionId']}/answer/{item['id']}"
            })

    return answers


async def main():
    print("="*60)
    print("知乎数据爬取 - JavaScript注入方案")
    print("="*60)
    print(f"输出目录: {OUTPUT_DIR}")
    print("="*60)

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=False,  # 可见模式便于调试
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
        )

        # 加载存储状态
        context = await browser.new_context(
            storage_state="data/zhihu_auth.json" if Path("data/zhihu_auth.json").exists() else None,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        # 注入反检测脚本
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        try:
            # 访问首页建立会话
            print("\n访问知乎首页...")
            await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 访问用户回答页面
            user_url = "https://www.zhihu.com/people/xu-ze-qiu/answers"
            print(f"\n访问用户页面: {user_url}")
            await page.goto(user_url, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # 提取数据
            print("\n提取页面数据...")
            answers = await extract_from_page(page)

            print(f"\n从初始页面提取到 {len(answers)} 条回答")

            # 如果数据量不够，尝试滚动加载更多
            if len(answers) < 100:
                print("\n滚动加载更多数据...")
                for i in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(3)

                    # 再次提取
                    new_answers = await extract_from_page(page)
                    if len(new_answers) > len(answers):
                        print(f"  滚动 {i+1} 次后: {len(new_answers)} 条")
                        answers = new_answers

            # 保存数据
            if answers:
                # 分批保存
                batch_size = 50
                for i in range(0, len(answers), batch_size):
                    batch = answers[i:i+batch_size]
                    save_batch(batch, i // batch_size)

                print(f"\n{'='*60}")
                print(f"✅ 爬取完成!")
                print(f"{'='*60}")
                print(f"  - 总计: {len(answers)} 条回答")
                print(f"  - 输出目录: {OUTPUT_DIR}")
                print(f"{'='*60}")
            else:
                print("\n⚠️ 未能获取到数据")

        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            input("\n按回车键关闭浏览器...")
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
