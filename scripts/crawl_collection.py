#!/usr/bin/env python3
"""
知乎收藏夹爬虫 - 支持分页爬取

用法:
    python scripts/crawl_collection.py --collection 860134416 --count 200
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.browser import BrowserManager
from utils.image_downloader import ImageDownloader


class CollectionCrawler:
    """收藏夹爬虫 - 支持分页"""

    def __init__(self, auth_file: str = "data/zhihu_auth.json", headless: bool = False):
        self.auth_file = auth_file
        self.headless = headless
        self.browser_manager: Optional[BrowserManager] = None
        self.page = None

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def init(self):
        self.browser_manager = BrowserManager(
            auth_file=self.auth_file,
            headless=self.headless,
        )
        await self.browser_manager.init()
        self.page = self.browser_manager.page

    async def close(self):
        if self.browser_manager:
            await self.browser_manager.close()

    async def crawl(
        self,
        collection_id: str,
        count: int = 200,
        item_type: str = "all",
        extract_images: bool = True,
        download_images: bool = True,
        image_quality: str = "hd",
        image_path: str = "output/images",
    ) -> List[Dict]:
        """爬取收藏夹 - 支持分页"""

        collection_url = f"https://www.zhihu.com/collection/{collection_id}"
        await self.page.goto(collection_url, wait_until="domcontentloaded")
        await asyncio.sleep(5)

        # 获取收藏夹信息
        info = await self.page.evaluate("""() => {
            const descEl = document.querySelector('[class*="description"]');
            const description = descEl ? descEl.innerText.trim() : '';
            return { description };
        }""")

        print(f"\n开始爬取收藏夹 {collection_id}...")
        print(f"  收藏夹信息: {info['description']}")
        print(f"  目标数量: {count}")
        print(f"  类型过滤: {item_type}")
        print("-" * 50)

        items = []
        page_num = 1

        while len(items) < count:
            print(f"\n--- 第 {page_num} 页 ---")

            # 获取当前页面内容
            new_items = await self.page.evaluate(
                """(itemType) => {
                const results = [];
                const allItems = document.querySelectorAll('.ContentItem');

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
                        const authorEl = item.querySelector('.AuthorInfo-name, a[href*="/people/"]');
                        if (authorEl) {
                            author = authorEl.innerText.trim();
                        }

                        // 获取点赞数
                        let voteCount = 0;
                        const voteEl = item.querySelector('.VoteButton');
                        if (voteEl) {
                            const voteText = voteEl.innerText.trim();
                            voteCount = parseInt(voteText.replace(/[^0-9]/g, '')) || 0;
                        }

                        // 获取内容摘要
                        const contentEl = item.querySelector('.RichText, [class*="excerpt"]');
                        const content = contentEl ? contentEl.innerText.trim() : '';

                        if (title && url) {
                            results.push({
                                title: title,
                                url: url,
                                item_type: type,
                                author: author,
                                content: content,
                                vote_count: voteCount
                            });
                        }
                    } catch (e) {}
                });

                return results;
            }""",
                item_type,
            )

            # 去重
            existing_urls = {item["url"] for item in items}
            new_count = 0
            for item in new_items:
                if item["url"] not in existing_urls:
                    items.append(item)
                    existing_urls.add(item["url"])
                    new_count += 1

            print(f"  本页新增: {new_count} 条, 总计: {len(items)} 条")

            if len(items) >= count:
                break

            # 尝试点击"下一页"
            try:
                # 查找下一页按钮 - 使用多个选择器尝试
                next_btn = None
                selectors = [
                    ".Pagination-next",
                    ".Paginator-next",
                    '[class*="next"]',
                    'button:has-text("下一页")',
                    'a:has-text("下一页")',
                ]
                for sel in selectors:
                    next_btn = await self.page.query_selector(sel)
                    if next_btn:
                        break

                if next_btn:
                    # 检查是否禁用（知乎用 CSS 类名和 aria-disabled 标记禁用状态）
                    is_disabled = await next_btn.get_attribute("disabled")
                    class_name = await next_btn.get_attribute("class") or ""
                    aria_disabled = await next_btn.get_attribute("aria-disabled")
                    if is_disabled or "disabled" in class_name or aria_disabled == "true":
                        print(f"  已到最后一页")
                        break

                    print(f"  点击下一页...")
                    await next_btn.click()
                    await asyncio.sleep(3)
                    page_num += 1
                else:
                    print(f"  未找到分页按钮，可能已到最后一页")
                    break

            except Exception as e:
                print(f"  翻页失败: {type(e).__name__}: {e}")
                break

        # 限制数量
        items = items[:count]

        print(f"\n获取完整内容 ({len(items)} 条)...")

        # 初始化图片下载器
        downloader = None
        if extract_images and download_images:
            downloader = ImageDownloader(
                base_path=image_path,
                quality=image_quality
            )
            await downloader.__aenter__()

        try:
            # 获取完整内容（阈值设为500，列表页摘要通常<200字符）
            for i, item in enumerate(items):
                if not item.get("content") or len(item.get("content", "")) < 500:
                    print(f"  [{i + 1}/{len(items)}] 获取: {item['title'][:30]}...")
                    try:
                        await self.page.goto(
                            item["url"], wait_until="domcontentloaded", timeout=30000
                        )
                        await asyncio.sleep(2)

                        # 滚动到页面底部触发懒加载
                        await self.page.evaluate(
                            "window.scrollTo(0, document.body.scrollHeight)"
                        )
                        await asyncio.sleep(1)

                        result = await self.page.evaluate("""(extractImages) => {
                            // 优先查找内容容器
                            let contentEl = null;
                            const containerSelectors = [
                                '.zm-item-answer, .AnswerItem, .ContentItem .AnswerItem',
                                '.article .RichText',
                                '.Post-content',
                                '.RichText'
                            ];

                            for (const sel of containerSelectors) {
                                const el = document.querySelector(sel);
                                if (el && el.innerText.trim().length > 30) {
                                    contentEl = el;
                                    break;
                                }
                            }

                            if (!contentEl) {
                                return { content: '', images: [] };
                            }

                            const contentHtml = contentEl.innerHTML;
                            const images = [];
                            let content = '';

                            // 递归遍历节点，按顺序提取内容和图片
                            function traverseNode(node) {
                                if (node.nodeType === Node.TEXT_NODE) {
                                    // 文本节点
                                    const text = node.textContent.trim();
                                    if (text) {
                                        content += text + ' ';
                                    }
                                } else if (node.nodeType === Node.ELEMENT_NODE) {
                                    if (node.tagName === 'IMG') {
                                        // 图片节点，只处理不遍历子节点
                                        if (extractImages) {
                                            let url = node.getAttribute('data-original') || node.src || '';
                                            if (url && url.startsWith('//')) {
                                                url = 'https:' + url;
                                            }

                                            if (url && (url.includes('zhimg.com') || url.startsWith('http'))) {
                                                const imgIndex = images.length;
                                                images.push({
                                                    url: url,
                                                    alt: node.alt || '',
                                                    width: node.width || 0,
                                                    height: node.height || 0,
                                                    position: content.length
                                                });
                                                // 在文本中插入图片标记
                                                content += `[图片：${imgIndex}] `;
                                            }
                                        }
                                        return; // img节点没有需要处理的子节点
                                    } else if (node.tagName === 'BR' || node.tagName === 'P' || node.tagName === 'DIV' || node.tagName === 'H1' || node.tagName === 'H2' || node.tagName === 'H3' || node.tagName === 'H4' || node.tagName === 'H5' || node.tagName === 'H6') {
                                        // 块级元素，添加换行
                                        content += '\\n';
                                    } else if (node.tagName === 'LI') {
                                        // 列表项
                                        content += '\\n- ';
                                    } else if (node.tagName === 'NOSCRIPT' || node.tagName === 'SCRIPT' || node.tagName === 'STYLE') {
                                        // 不需要处理的标签，跳过子节点
                                        return;
                                    }

                                    // 遍历子节点
                                    for (const child of node.childNodes) {
                                        traverseNode(child);
                                    }

                                    // 块级元素结束后添加换行
                                    if (node.tagName === 'P' || node.tagName === 'DIV' || node.tagName === 'H1' || node.tagName === 'H2' || node.tagName === 'H3' || node.tagName === 'H4' || node.tagName === 'H5' || node.tagName === 'H6') {
                                        content += '\\n';
                                    }
                                }
                            }

                            traverseNode(contentEl);

                            // 清理多余的换行和空格
                            content = content.replace(/\\n{3,}/g, '\\n\\n').trim();

                            return {
                                content: content,
                                content_html: contentHtml,
                                images: images
                            };
                        }""", extract_images)

                        if result.get('content'):
                            item["content"] = result['content']

                        if extract_images:
                            item["content_html"] = result.get('content_html', '')
                            item["images"] = result.get('images', [])

                            # 下载图片
                            if download_images and downloader and item["images"]:
                                # 从URL提取回答/文章ID
                                url = item.get("url", "")
                                item_id = ""
                                if "/answer/" in url:
                                    item_id = url.split("/answer/")[-1].split("/")[0]
                                elif "/article/" in url:
                                    item_id = url.split("/article/")[-1].split("/")[0]

                                if item_id:
                                    print(f"      下载 {len(item['images'])} 张图片...")
                                    sub_dir = f"collection_{collection_id}"
                                    item["images"] = await downloader.download_images(
                                        item["images"],
                                        sub_dir=sub_dir,
                                        answer_id=item_id
                                    )

                                    # 将图片标记插入到内容中
                                    item["content"] = downloader.insert_images_into_content(
                                        item["content"],
                                        item["images"]
                                    )

                        if (i + 1) % 10 == 0:
                            print(f"      >>> 已处理 {i + 1} 条")

                        await asyncio.sleep(1.5)

                    except Exception as e:
                        print(f"      错误: {type(e).__name__}: {e}")
        finally:
            if downloader:
                await downloader.__aexit__()

        print(f"\n✓ 完成! 共获取 {len(items)} 条")

        return items

    def save_results(self, items: List[Dict], output_file: str):
        """保存结果"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

        # 统计
        answers = sum(1 for i in items if i.get("item_type") == "answer")
        articles = sum(1 for i in items if i.get("item_type") == "article")
        print(f"  回答: {answers}, 文章: {articles}")


async def main():
    parser = argparse.ArgumentParser(description="知乎收藏夹爬虫 - 支持分页")
    parser.add_argument("--collection", type=str, required=True, help="收藏夹ID")
    parser.add_argument("--count", type=int, default=200, help="爬取数量")
    parser.add_argument(
        "--type",
        type=str,
        default="all",
        choices=["all", "answer", "article"],
        help="类型过滤",
    )
    parser.add_argument(
        "--output", type=str, default="output/collection_{id}.json", help="输出文件"
    )
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument(
        "--no-extract-images",
        action="store_true",
        help="关闭图片URL提取功能（默认开启）",
    )
    parser.add_argument(
        "--no-download-images",
        action="store_true",
        help="关闭图片本地下载功能（默认开启）",
    )
    parser.add_argument(
        "--image-quality",
        type=str,
        default="hd",
        choices=["raw", "hd", "normal", "thumbnail"],
        help="图片质量 (raw:原图, hd:高清, normal:普通, thumbnail:缩略图，默认hd)",
    )
    parser.add_argument(
        "--image-path",
        type=str,
        default="output/images",
        help="图片存储路径（默认 output/images）",
    )

    args = parser.parse_args()

    output_file = args.output.format(id=args.collection)

    async with CollectionCrawler(headless=args.headless) as crawler:
        items = await crawler.crawl(
            collection_id=args.collection,
            count=args.count,
            item_type=args.type,
            extract_images=not args.no_extract_images,
            download_images=not args.no_download_images,
            image_quality=args.image_quality,
            image_path=args.image_path,
        )

        crawler.save_results(items, output_file)


if __name__ == "__main__":
    asyncio.run(main())
