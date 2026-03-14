#!/usr/bin/env python3
"""
最终版爬取方案 - 使用GraphQL API直接获取
通过分析知乎API，使用其内部GraphQL接口获取数据
"""
import asyncio
import json
import re
import time
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
    print(f"  [保存] 批次 #{batch_index}: {len(answers)} 条")


async def fetch_answers_via_api(page, user_id="xu-ze-qiu"):
    """通过GraphQL API获取回答"""
    answers = []
    offset = 0
    limit = 20
    has_more = True

    print(f"\n开始通过API获取回答...")

    while has_more and len(answers) < 5000:
        try:
            # 构建GraphQL查询
            graphql_query = {
                "operationName": "ProfileAnsweres",
                "variables": {
                    "urlToken": user_id,
                    "offset": offset,
                    "limit": limit
                },
                "query": """query ProfileAnsweres($urlToken: String!, $offset: Int!, $limit: Int!) {
                    user(urlToken: $urlToken) {
                        answers(offset: $offset, limit: $limit) {
                            data {
                                id
                                content
                                createdTime
                                updatedTime
                                voteupCount
                                commentCount
                                question {
                                    id
                                    title
                                }
                            }
                            paging {
                                isEnd
                                next
                                totals
                            }
                        }
                    }
                }"""
            }

            # 在页面中执行GraphQL查询
            result = await page.evaluate("""async (query) => {
                try {
                    const response = await fetch('https://www.zhihu.com/graphql', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'x-apollo-operation-name': 'ProfileAnsweres'
                        },
                        body: JSON.stringify(query)
                    });
                    return await response.json();
                } catch (e) {
                    return { error: e.message };
                }
            }""", graphql_query)

            if result.get('error'):
                print(f"  查询错误: {result['error']}")
                break

            data = result.get('data', {})
            user_data = data.get('user', {})
            answers_data = user_data.get('answers', {})
            answers_list = answers_data.get('data', [])
            paging = answers_data.get('paging', {})

            # 解析回答
            for ans in answers_list:
                question = ans.get('question', {})
                answers.append({
                    'id': str(ans.get('id', '')),
                    'type': 'answer',
                    'question': {
                        'id': str(question.get('id', '')),
                        'title': question.get('title', '')
                    },
                    'content': ans.get('content', ''),
                    'voteup_count': ans.get('voteupCount', 0),
                    'comment_count': ans.get('commentCount', 0),
                    'created_time': ans.get('createdTime', 0),
                    'url': f"https://www.zhihu.com/question/{question.get('id', '')}/answer/{ans.get('id', '')}"
                })

            print(f"  已获取: {len(answers)} 条 (本次 +{len(answers_list)})")

            # 检查是否还有更多
            has_more = not paging.get('isEnd', True)
            offset += limit

            # 延迟避免请求过快
            await asyncio.sleep(2)

        except Exception as e:
            print(f"  获取失败: {e}")
            import traceback
            traceback.print_exc()
            break

    return answers


async def main():
    print("="*60)
    print("知乎数据爬取 - GraphQL API方案")
    print("="*60)
    print(f"输出目录: {OUTPUT_DIR}")
    print("="*60)

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        # 加载登录状态
        context = await browser.new_context(
            storage_state="data/zhihu_auth.json" if Path("data/zhihu_auth.json").exists() else None,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        try:
            # 访问首页
            print("\n访问知乎首页...")
            await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 访问用户页面
            print("访问用户页面...")
            await page.goto("https://www.zhihu.com/people/xu-ze-qiu", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # 使用GraphQL API获取回答
            answers = await fetch_answers_via_api(page)

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
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()
            print("\n浏览器已关闭")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n程序出错: {e}")
        import traceback
        traceback.print_exc()
