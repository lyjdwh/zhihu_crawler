#!/usr/bin/env python3
"""
知乎收藏夹爬虫 - 爬取收藏夹中的回答和文章

用法:
    # 爬取收藏夹
    python scripts/crawl_collection.py --collection 860134416

    # 爬取指定数量
    python scripts/crawl_collection.py --collection 860134416 --count 100

    # 爬取并按类型过滤
    python scripts/crawl_collection.py --collection 860134416 --type answer
    python scripts/crawl_collection.py --collection 860134416 --type article
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


@dataclass
class CollectionItem:
    """收藏夹条目"""
    title: str
    url: str
    item_type: str  # answer 或 article
    author: str
    author_url: str
    content: str
    vote_count: int
    created_time: str = ""


class CollectionCrawler:
    """收藏夹爬虫"""

    def __init__(self, auth_file: str = "data/zhihu_auth.json", headless: bool = False):
        self.auth_file = auth_file
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def init(self):
        playwright = await async_playwright().start()

        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )

        context_options = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "viewport": {"width": 1920, "height": 1080},
        }

        if os.path.exists(self.auth_file):
            context_options["storage_state"] = self.auth_file

        self.context = await self.browser.new_context(**context_options)

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(60000)

        await self.page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)

    async def close(self):
        if self.browser:
            await self.browser.close()

    def get_collection_info(self, collection_id: str) -> Dict:
        """获取收藏夹信息"""
        # 访问收藏夹页面
        url = f"https://www.zhihu.com/collection/{collection_id}"
        return {
            "id": collection_id,
            "url": url
        }

    async def crawl(
        self,
        collection_id: str,
        count: int = 100,
        item_type: str = "all"  # all/answer/article
    ) -> List[Dict]:
        """爬取收藏夹"""

        collection_url = f"https://www.zhihu.com/collection/{collection_id}"
        await self.page.goto(collection_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        print(f"\n开始爬取收藏夹 {collection_id}...")
        print(f"  目标数量: {count}")
        print(f"  类型过滤: {item_type}")
        print("-" * 50)

        items = []
        scroll_count = 0
        max_scrolls = 30

        while len(items) < count and scroll_count < max_scrolls:
            # 获取已有的URL列表
            existing_urls_list = [item['url'] for item in items]

            # 将参数传入JavaScript
            js_args = {"existingUrls": existing_urls_list, "itemType": item_type}

            new_items = await self.page.evaluate("""
                (params) => {
                const existingUrls = params.existingUrls;
                const itemType = params.itemType;

                const results = [];
                const allItems = document.querySelectorAll('.List-item, [class*="Item"], [class*="Collection"], .CollectionItem');

                allItems.forEach(item => {
                    try {
                        // 尝试找回答链接
                        let link = item.querySelector('a[href*="/answer/"]');
                        let type = 'answer';

                        // 如果没有回答链接，尝试文章链接
                        if (!link) {
                            link = item.querySelector('a[href*="/article/"]');
                            type = 'article';
                        }

                        if (!link) return;

                        const title = link.innerText.trim();
                        const url = link.href;

                        // 过滤类型
                        if (itemType !== 'all' && type !== itemType) return;

                        // 获取作者
                        let author = '';
                        let authorUrl = '';
                        const authorEl = item.querySelector('.AuthorInfo-name, [class*="author"] a, a[href*="/people/"]');
                        if (authorEl) {
                            author = authorEl.innerText.trim();
                            authorUrl = authorEl.href || '';
                        }

                        // 获取点赞数
                        let voteCount = 0;
                        const voteEl = item.querySelector('.VoteButton, [class*="vote"]');
                        if (voteEl) {
                            const voteText = voteEl.innerText.trim();
                            voteCount = parseInt(voteText.replace(/[^0-9]/g, '')) || 0;
                        }

                        // 获取内容摘要
                        const contentEl = item.querySelector('.RichText, .content, [class*="excerpt"]');
                        const content = contentEl ? contentEl.innerText.trim() : '';

                        if (title && url && !existingUrls.includes(url)) {
                            results.push({
                                title: title,
                                url: url,
                                item_type: type,
                                author: author,
                                author_url: authorUrl,
                                content: content,
                                vote_count: voteCount
                            });
                        }
                    } catch (e) {}
                });

                return results;
            }""", js_args)

            # 去重
            existing_urls_list = [item['url'] for item in items]
            for item in new_items:
                if item['url'] not in existing_urls_list:
                    items.append(item)
                    existing_urls_list.append(item['url'])

            scroll_count += 1
            print(f"  滚动 {scroll_count}: 共 {len(items)} 条")

            if len(items) >= count:
                break

            await self.page.evaluate("window.scrollBy(0, 1200);")
            await asyncio.sleep(2)

        # 限制数量
        items = items[:count]

        # 获取完整内容
        print(f"\n获取完整内容 ({len(items)} 条)...")
        await self._fetch_content(items)

        print(f"\n✓ 完成! 共获取 {len(items)} 条")

        return items

    async def _fetch_content(self, items: List[Dict]):
        """获取每个条目的完整内容"""
        for i, item in enumerate(items):
            url = item.get('url', '')
            title = item.get('title', '')[:35]

            print(f"  [{i+1}/{len(items)}] {title}...")

            try:
                await self.page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                content = await self.page.evaluate("""() => {
                    // 尝试多种选择器
                    const selectors = [
                        '.zm-item-answer .RichText',
                        '.AnswerItem .RichText',
                        '.article .RichText',
                        '.Post-content',
                        '.RichText'
                    ];

                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 30) {
                            return el.innerText.trim();
                        }
                    }

                    return '';
                }""")

                if content:
                    item['content'] = content

                if (i + 1) % 10 == 0:
                    print(f"      >>> 已处理 {i+1} 条")

                await asyncio.sleep(1.5)

            except Exception as e:
                print(f"      错误: {str(e)[:30]}")

    def save_results(self, items: List[Dict], output_file: str):
        """保存结果"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

        # 统计
        answers = sum(1 for i in items if i.get('item_type') == 'answer')
        articles = sum(1 for i in items if i.get('item_type') == 'article')
        print(f"  回答: {answers}, 文章: {articles}")


async def main():
    parser = argparse.ArgumentParser(description="知乎收藏夹爬虫")
    parser.add_argument("--collection", type=str, required=True, help="收藏夹ID")
    parser.add_argument("--count", type=int, default=100, help="爬取数量")
    parser.add_argument("--type", type=str, default="all", choices=["all", "answer", "article"], help="类型过滤")
    parser.add_argument("--output", type=str, default="output/collection_{id}.json", help="输出文件")
    parser.add_argument("--headless", action="store_true", help="无头模式")

    args = parser.parse_args()

    # 处理输出路径
    output_file = args.output.format(id=args.collection)

    async with CollectionCrawler(headless=args.headless) as crawler:
        items = await crawler.crawl(
            collection_id=args.collection,
            count=args.count,
            item_type=args.type
        )

        crawler.save_results(items, output_file)


if __name__ == "__main__":
    asyncio.run(main())