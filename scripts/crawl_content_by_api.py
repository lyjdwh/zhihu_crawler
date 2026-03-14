#!/usr/bin/env python3
"""
知乎回答内容爬取脚本 - 通过API获取内容
利用已有的回答ID，直接调用知乎API获取回答完整内容
"""

import asyncio
import json
import glob
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


async def get_answer_content_via_browser(page, answer_id: str) -> dict:
    """通过浏览器中的fetch请求获取回答内容"""

    # 使用 page.evaluate 发起 API 请求
    result = await page.evaluate(f"""async () => {{
        try {{
            const url = `https://www.zhihu.com/api/v4/answers/${{{answer_id}}}?include=content,question,voteup_count,comment_count,created_time`;

            const response = await fetch(url, {{
                method: 'GET',
                credentials: 'include',
                headers: {{
                    'accept': 'application/json, text/plain, */*',
                    'x-requested-with': 'fetch',
                    'x-zse-93': '101_3_3.0'
                }}
            }});

            if (!response.ok) {{
                return {{ success: false, status: response.status }};
            }}

            const data = await response.json();
            return {{ success: true, data }};
        }} catch (err) {{
            return {{ success: false, error: err.message }};
        }}
    }}""")

    if result and result.get("success"):
        data = result["data"]
        return {
            "id": str(data.get("id", "")),
            "content": data.get("content", ""),
            "question": {
                "id": str(data.get("question", {}).get("id", "")),
                "title": data.get("question", {}).get("title", "")
            },
            "voteup_count": data.get("voteup_count", 0),
            "comment_count": data.get("comment_count", 0),
            "created_time": data.get("created_time", 0),
            "url": f"https://www.zhihu.com/question/{data.get('question', {}).get('id', '')}/answer/{data.get('id', '')}"
        }
    return None


async def main():
    """主函数"""

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 读取已有的回答ID
    all_ids = []
    files = sorted(output_dir.glob("奥特之父_answers_batch_*.json"))
    for f in files:
        with open(f, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
            for item in data:
                answer_id = item.get('id', '')
                if answer_id and answer_id != 'None':
                    all_ids.append(answer_id)

    print(f"已有 {len(all_ids)} 个回答ID")

    # 检查哪些已经有内容
    full_file = output_dir / "奥特之父_answers_full.json"
    existing_ids = set()
    if full_file.exists():
        with open(full_file, 'r', encoding='utf-8') as fp:
            existing_data = json.load(fp)
            for item in existing_data:
                if item.get('content'):
                    existing_ids.add(item.get('id'))

    # 需要获取内容的ID
    ids_to_fetch = [id for id in all_ids if id not in existing_ids]
    print(f"需要获取内容: {len(ids_to_fetch)} 个")

    if not ids_to_fetch:
        print("所有回答已有内容!")
        return

    # 初始化浏览器
    auth_file = "data/zhihu_auth.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context_options = {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
        }

        if os.path.exists(auth_file):
            context_options["storage_state"] = auth_file

        context = await browser.new_context(**context_options)
        page = await context.new_page()

        # 访问知乎建立会话
        await page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # 批量获取内容
        results = []
        success_count = 0
        fail_count = 0

        for i, answer_id in enumerate(ids_to_fetch):
            print(f"[{i+1}/{len(ids_to_fetch)}] 获取回答 {answer_id}...")

            result = await get_answer_content_via_browser(page, answer_id)

            if result:
                results.append(result)
                success_count += 1
            else:
                fail_count += 1

            # 每20条保存一次
            if (i + 1) % 20 == 0:
                # 保存到临时文件
                temp_file = output_dir / f"temp_content_{i+1}.json"
                with open(temp_file, 'w', encoding='utf-8') as fp:
                    json.dump(results, fp, ensure_ascii=False, indent=2)
                print(f"  [保存] {len(results)} 条到 {temp_file.name}")

            # 请求间隔
            await asyncio.sleep(2)

        # 合并所有数据
        print(f"\n获取完成: 成功 {success_count}, 失败 {fail_count}")

        # 读取之前已有的数据
        all_data = []
        for f in files:
            with open(f, 'r', encoding='utf-8') as fp:
                batch = json.load(fp)
                for item in batch:
                    # 如果已有新内容，用新的替换
                    new_item = next((r for r in results if r['id'] == item['id']), None)
                    if new_item:
                        all_data.append(new_item)
                    else:
                        all_data.append(item)

        # 添加新增的结果
        for r in results:
            if not any(d['id'] == r['id'] for d in all_data):
                all_data.append(r)

        # 保存完整数据
        with open(full_file, 'w', encoding='utf-8') as fp:
            json.dump(all_data, fp, ensure_ascii=False, indent=2)

        print(f"\n已保存到: {full_file}")
        print(f"总计 {len(all_data)} 条回答")

        # 统计有内容的数量
        with_content = sum(1 for d in all_data if d.get('content'))
        print(f"其中有内容的: {with_content} 条")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())