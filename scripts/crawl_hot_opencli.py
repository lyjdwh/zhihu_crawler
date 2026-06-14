#!/usr/bin/env python3
"""
知乎热榜爬虫 (OpenCLI 版) - 通过 opencli 获取知乎热榜

Playwright 爬虫没有这个功能，是 OpenCLI 独有的新能力。

用法:
    python scripts/crawl_hot_opencli.py
    python scripts/crawl_hot_opencli.py --limit 10
    python scripts/crawl_hot_opencli.py --limit 30 --output hot.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.opencli_runner import (
    OpenCLIRunner,
    OpenCLIError,
    OpenCLIAuthError,
    OpenCLINotFoundError,
    create_runner_from_config,
)
from core.config import OPENCLI_CONFIG


class HotCrawlerOpenCLI:
    """知乎热榜爬虫 (OpenCLI 后端)"""

    def __init__(self, runner: Optional[OpenCLIRunner] = None):
        self.runner = runner or create_runner_from_config()

    def crawl(self, limit: int = 20) -> List[Dict]:
        """获取知乎热榜

        Args:
            limit: 返回条目数

        Returns:
            热榜列表，每项字段: rank, title, heat, answers
        """
        print(f"\n获取知乎热榜 (OpenCLI)...")
        print(f"  返回数量: {limit}")
        print("-" * 50)

        try:
            hot_list = self.runner.zhihu_hot(limit=limit)
            print(f"\n✓ 获取到 {len(hot_list)} 条热榜")
            return hot_list
        except OpenCLIAuthError as e:
            print(f"认证错误: {e}")
            return []
        except OpenCLIError as e:
            print(f"OpenCLI 错误: {e}")
            return []

    def save_results(self, hot_list: List[Dict], output_file: str):
        """保存结果到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 添加元数据
        data = {
            "crawled_at": datetime.now().isoformat(),
            "source": "opencli zhihu hot",
            "count": len(hot_list),
            "items": hot_list,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

        # 打印摘要
        print(f"\n热榜前10:")
        for item in hot_list[:10]:
            rank = item.get("rank", "?")
            title = item.get("title", "")[:50]
            heat = item.get("heat", "")
            print(f"  {rank:>2}. {title}  (热度: {heat})")


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description="知乎热榜爬虫 (OpenCLI 版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/crawl_hot_opencli.py
  python scripts/crawl_hot_opencli.py --limit 30
  python scripts/crawl_hot_opencli.py --limit 10 --output output/hot.json

前置条件:
  1. 安装 opencli: npm install -g opencli
  2. 初始化浏览器会话: opencli browser zhihu init
  3. 在打开的浏览器窗口中登录知乎
        """,
    )

    parser.add_argument("--limit", type=int, default=20, help="返回数量 (默认20)")
    parser.add_argument(
        "--output", type=str, default="output/zhihu_hot.json", help="输出文件"
    )

    args = parser.parse_args()

    crawler = HotCrawlerOpenCLI()

    try:
        hot_list = crawler.crawl(limit=args.limit)

        if hot_list:
            crawler.save_results(hot_list, args.output)
        else:
            print("\n⚠ 未获取到热榜数据")
            print("请确认:")
            print(f"  1. opencli 已安装 (当前版本: opencli --version)")
            print(f"  2. 浏览器会话已初始化: opencli browser {OPENCLI_CONFIG['browser_session']} init")
            print(f"  3. 知乎已登录")

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
