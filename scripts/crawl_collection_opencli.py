#!/usr/bin/env python3
"""
知乎收藏夹爬虫 (OpenCLI 版) - 通过 opencli 浏览器桥接获取收藏夹内容

与 Playwright 版 (crawl_collection.py) 功能对齐。

用法:
    python scripts/crawl_collection_opencli.py --collection 860134416 --count 200
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.opencli_runner import (
    OpenCLIRunner,
    OpenCLIConfig,
    OpenCLIError,
    OpenCLIAuthError,
    OpenCLITimeoutError,
    OpenCLINotFoundError,
    create_runner_from_config,
)
from core.config import OPENCLI_CONFIG


class CollectionCrawlerOpenCLI:
    """收藏夹爬虫 (OpenCLI 后端)"""

    def __init__(
        self,
        runner: Optional[OpenCLIRunner] = None,
    ):
        """
        Args:
            runner: OpenCLIRunner 实例
        """
        self.runner = runner or create_runner_from_config()

    def crawl(
        self,
        collection_id: str,
        count: int = 200,
        item_type: str = "all",
        extract_images: bool = False,
        download_images: bool = False,
        image_quality: str = "hd",
        image_path: str = "output/images",
    ) -> List[Dict]:
        """
        爬取收藏夹内容（分页）

        Args:
            collection_id: 收藏夹 ID
            count: 目标数量
            item_type: 类型过滤 (all/answer/article)
            extract_images: 是否提取图片
            download_images: 是否下载图片
            image_quality: 图片质量
            image_path: 图片路径

        Returns:
            条目列表
        """
        print(f"\n开始爬取收藏夹 {collection_id} (OpenCLI)...")
        print(f"  目标数量: {count}")
        print(f"  类型过滤: {item_type}")
        print("-" * 50)

        items = []
        offset = 0
        page_limit = 20  # opencli collection 每页最大 20
        page_num = 1

        while len(items) < count:
            print(f"\n--- 第 {page_num} 页 (offset={offset}) ---")

            try:
                # 调用 opencli zhihu collection
                page_items = self.runner.zhihu_collection(
                    collection_id,
                    offset=offset,
                    limit=min(page_limit, count - len(items)),
                )

                if not page_items:
                    print("  无更多内容")
                    break

                # 去重并过滤类型
                seen_urls = {item.get("url", "") for item in items}
                new_count = 0
                for item in page_items:
                    url = item.get("url", "")
                    if url in seen_urls:
                        continue

                    item_type_value = item.get("type", "")
                    if item_type != "all" and item_type_value != item_type:
                        continue

                    items.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "item_type": item_type_value,
                        "author": item.get("author", ""),
                        "content": item.get("excerpt", ""),  # 摘要
                        "vote_count": item.get("votes", 0),
                        "source_backend": "opencli",
                    })
                    seen_urls.add(url)
                    new_count += 1

                print(f"  本页新增: {new_count} 条, 总计: {len(items)} 条")

                if len(page_items) < page_limit:
                    print("  已到最后一页")
                    break

                offset += page_limit
                page_num += 1

                if len(items) >= count:
                    break

                time.sleep(1.5)

            except OpenCLIAuthError as e:
                print(f"  认证错误: {e}")
                break
            except OpenCLIError as e:
                print(f"  OpenCLI 错误: {e}")
                break

        # 限制数量
        items = items[:count]

        # 获取完整内容（摘要不足的条目）
        self._fetch_full_content(items, collection_id)

        print(f"\n✓ 完成! 共获取 {len(items)} 条")
        return items

    def _fetch_full_content(self, items: List[Dict], collection_id: str):
        """对摘要不足的条目获取完整内容"""
        need_content = [
            (i, item)
            for i, item in enumerate(items)
            if not item.get("content") or len(item.get("content", "")) < 500
        ]

        if not need_content:
            return

        print(f"\n获取完整内容 ({len(need_content)} 条)...")

        for idx, (orig_idx, item) in enumerate(need_content):
            url = item.get("url", "")
            title = item.get("title", "")[:35]

            # 从 URL 提取 answer_id
            answer_id = ""
            if "/answer/" in url:
                answer_id = url.split("/answer/")[-1].split("/")[0].split("?")[0]

            if not answer_id:
                continue

            print(f"  [{idx + 1}/{len(need_content)}] {title}...")

            try:
                detail = self.runner.zhihu_answer_detail(answer_id)
                if detail:
                    converted = OpenCLIRunner.convert_answer_detail_to_legacy(detail)
                    if converted:
                        item["content"] = converted.get("content", "")
                        item["vote_count"] = item.get("vote_count") or converted.get(
                            "vote_count", 0
                        )
                        item["author"] = item.get("author") or converted.get("author", "")

                if (idx + 1) % 10 == 0:
                    print(f"      >>> 已处理 {idx + 1} 条")

                time.sleep(1.5)

            except OpenCLIAuthError as e:
                print(f"      认证错误: {e}")
                break
            except OpenCLITimeoutError as e:
                print(f"      超时: {e}，重试中...")
                try:
                    detail = self.runner.zhihu_answer_detail(answer_id)
                    if detail:
                        converted = OpenCLIRunner.convert_answer_detail_to_legacy(detail)
                        item["content"] = converted.get("content", "")
                except Exception:
                    print(f"      重试失败，跳过")
            except OpenCLIError as e:
                print(f"      OpenCLI 错误: {e}")
            except Exception as e:
                print(f"      错误: {type(e).__name__}: {e}")

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


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description="知乎收藏夹爬虫 (OpenCLI 版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/crawl_collection_opencli.py --collection 860134416 --count 200

前置条件:
  1. 安装 opencli: npm install -g opencli
  2. 初始化浏览器会话: opencli browser zhihu init
  3. 在打开的浏览器窗口中登录知乎
        """,
    )

    parser.add_argument("--collection", type=str, required=True, help="收藏夹 ID")
    parser.add_argument("--count", type=int, default=200, help="爬取数量")
    parser.add_argument(
        "--type",
        type=str,
        default="all",
        choices=["all", "answer", "article"],
        help="类型过滤",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/collection_{id}_opencli.json",
        help="输出文件",
    )
    parser.add_argument(
        "--no-extract-images",
        action="store_true",
        help="关闭图片URL提取功能",
    )
    parser.add_argument(
        "--no-download-images",
        action="store_true",
        help="关闭图片本地下载功能",
    )
    parser.add_argument(
        "--image-quality",
        type=str,
        default="hd",
        choices=["raw", "hd", "normal", "thumbnail"],
        help="图片质量 (默认hd)",
    )
    parser.add_argument(
        "--image-path",
        type=str,
        default="output/images",
        help="图片存储路径",
    )

    args = parser.parse_args()

    output_file = args.output.format(id=args.collection)

    crawler = CollectionCrawlerOpenCLI()

    try:
        items = crawler.crawl(
            collection_id=args.collection,
            count=args.count,
            item_type=args.type,
            extract_images=not args.no_extract_images,
            download_images=not args.no_download_images,
            image_quality=args.image_quality,
            image_path=args.image_path,
        )

        crawler.save_results(items, output_file)

    except OpenCLIAuthError as e:
        print(f"\n✗ 认证失败: {e}")
        print("请在 Chrome 中打开知乎并登录，然后运行:")
        print(f"  opencli browser {OPENCLI_CONFIG['browser_session']} bind")
        sys.exit(1)
    except OpenCLINotFoundError as e:
        print(f"\n✗ {e}")
        print("请安装 opencli: npm install -g opencli")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(0)


if __name__ == "__main__":
    main()
