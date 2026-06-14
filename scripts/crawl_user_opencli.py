#!/usr/bin/env python3
"""
知乎用户回答爬虫 (OpenCLI 版) - 通过 opencli 浏览器桥接获取数据

与 Playwright 版 (crawl_user.py) 功能对齐，但无需维护 Playwright 代码和 auth storage。

用法:
    python scripts/crawl_user_opencli.py --user xu-ze-qiu
    python scripts/crawl_user_opencli.py --user xu-ze-qiu --count 50 --topic finance
    python scripts/crawl_user_opencli.py --user xu-ze-qiu --after-date 2026-03-01 --topic finance
"""

import asyncio
import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime
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
from core.filters import check_topic, parse_zhihu_date
from core.config import OPENCLI_CONFIG
from utils.checkpoint import CheckpointManager
from utils.image_downloader import ImageDownloader


class ZhihuUserCrawlerOpenCLI:
    """知乎用户回答爬虫 (OpenCLI 后端)"""

    def __init__(
        self,
        runner: Optional[OpenCLIRunner] = None,
        config: Optional[OpenCLIConfig] = None,
    ):
        """
        Args:
            runner: OpenCLIRunner 实例，为 None 时自动创建
            config: OpenCLI 配置
        """
        self.runner = runner or OpenCLIRunner(config)
        self._download_semaphore = None  # 用于控制并发

    def crawl_answers(
        self,
        user_token: str,
        count: int = 100,
        topic: str = "all",
        after_date: Optional[str] = None,
        before_date: Optional[str] = None,
        with_content: bool = True,
        resume: bool = False,
        checkpoint: Optional[CheckpointManager] = None,
        extract_images: bool = True,
        download_images: bool = True,
        image_quality: str = "hd",
        image_path: str = "output/images",
    ) -> List[Dict]:
        """
        爬取用户回答

        Args:
            user_token: 用户 url_token
            count: 目标数量
            topic: 主题过滤
            after_date: 起始日期 (YYYY-MM-DD)
            before_date: 结束日期 (YYYY-MM-DD)
            with_content: 是否获取完整内容
            resume: 是否从断点继续
            checkpoint: 检查点管理器
            extract_images: 是否提取图片 URL
            download_images: 是否下载图片到本地
            image_quality: 图片质量
            image_path: 图片存储路径

        Returns:
            回答列表
        """
        all_answers = []
        scroll_count = 0

        # 检查点恢复
        if resume and checkpoint:
            saved_progress = checkpoint.get(f"{user_token}_progress_opencli", {})
            if saved_progress:
                scroll_count = saved_progress.get("scroll_count", 0)
                all_answers = saved_progress.get("answers", [])
                print(
                    f"\n[断点续传] 从滚动 {scroll_count} 继续，已获取 {len(all_answers)} 条回答"
                )

        # 解析日期
        after_dt = None
        before_dt = None
        if after_date:
            after_dt = datetime.strptime(after_date, "%Y-%m-%d")
        if before_date:
            before_dt = datetime.strptime(before_date, "%Y-%m-%d")

        print(f"\n开始爬取用户 {user_token} 的回答 (OpenCLI)...")
        print(f"  目标数量: {count}")
        print(f"  主题过滤: {topic}")
        if after_date:
            print(f"  日期筛选: {after_date} 之后")
        if before_date:
            print(f"  日期筛选: {before_date} 之前")
        print(f"  后端: OpenCLI v{self._get_opencli_version()}")
        print("-" * 50)

        # Phase 1: 列表发现 - 通过 opencli zhihu user-answers 获取用户回答列表
        # 纯 zhihu 命令，无需 browser 子系统
        all_answers = self._discover_answers_from_page(
            user_token=user_token,
            target_count=count,
            topic=topic,
            after_dt=after_dt,
            before_dt=before_dt,
            all_answers=all_answers,
            scroll_count=scroll_count,
            checkpoint=checkpoint,
        )

        # 限制数量
        all_answers = all_answers[:count]

        # Phase 2: 获取完整内容
        if with_content and all_answers:
            print(f"\n获取完整内容 ({len(all_answers)} 条)...")
            self._fetch_full_content(
                all_answers,
                extract_images=extract_images,
                download_images=download_images,
                image_quality=image_quality,
                image_path=image_path,
                user_token=user_token,
            )

        print(f"\n✓ 完成! 共获取 {len(all_answers)} 条回答")

        return all_answers

    def _get_opencli_version(self) -> str:
        """获取 opencli 版本"""
        try:
            import subprocess
            result = subprocess.run(
                [self.runner.config.binary_path, "--version"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def _discover_answers_from_page(
        self,
        user_token: str,
        target_count: int,
        topic: str,
        after_dt: Optional[datetime],
        before_dt: Optional[datetime],
        all_answers: List[Dict],
        scroll_count: int,
        checkpoint: Optional[CheckpointManager],
    ) -> List[Dict]:
        """从用户回答页面提取回答列表（Phase 1: 列表发现）"""
        max_scrolls = max(30, (target_count // 10) + 5)
        no_new_count = 0
        existing_ids = set(a["answer_id"] for a in all_answers)

        while len(all_answers) < target_count and scroll_count < max_scrolls:
            # 使用 browser eval 从 DOM 提取回答列表
            answers = self.runner.get_user_answers_from_page(user_token)

            # 如果不是第一页，在 eval 之前已经 scroll 过
            if scroll_count > 0:
                # 追加模式，但要过滤已有 ID
                pass

            for ans in answers:
                aid = ans.get("answer_id", "")
                if aid in existing_ids:
                    continue

                # 主题过滤
                text = ans.get("question_title", "")
                if not check_topic(text, topic):
                    continue

                # 日期过滤
                if after_dt or before_dt:
                    created = ans.get("created_time", "")
                    if created:
                        answer_dt = parse_zhihu_date(created)
                        if answer_dt:
                            if after_dt and answer_dt < after_dt:
                                continue
                            if before_dt and answer_dt > before_dt:
                                continue

                all_answers.append({
                    "answer_id": aid,
                    "question_id": ans.get("question_id", ""),
                    "question_title": text,
                    "question_url": f"https://www.zhihu.com/question/{ans.get('question_id', '')}/answer/{aid}",
                    "created_time": ans.get("created_time", ""),
                    "content": "",
                    "vote_count": 0,
                    "source_backend": "opencli",
                })
                existing_ids.add(aid)

            prev_count = len(all_answers)
            scroll_count += 1
            print(f"  滚动 {scroll_count}: 共 {len(all_answers)} 条匹配的回答")

            if len(all_answers) >= target_count:
                break

            # 连续 5 次无新内容，停止
            if len(all_answers) == prev_count:
                no_new_count += 1
                if no_new_count >= 5:
                    print(f"  连续 {no_new_count} 次无新内容，停止滚动")
                    break
            else:
                no_new_count = 0

            # 滚动加载更多
            try:
                self.runner.browser_scroll("down")
                self.runner.browser_wait("time", "2")
            except OpenCLIError as e:
                print(f"  滚动出错: {e}")
                break

            # 保存检查点
            if checkpoint:
                checkpoint.set(
                    f"{user_token}_progress_opencli",
                    {
                        "scroll_count": scroll_count,
                        "answers": all_answers,
                        "timestamp": datetime.now().isoformat(),
                    },
                )

        return all_answers

    def _fetch_full_content(
        self,
        answers: List[Dict],
        extract_images: bool = True,
        download_images: bool = True,
        image_quality: str = "hd",
        image_path: str = "output/images",
        user_token: str = "",
    ):
        """获取回答完整内容（Phase 2: 内容获取 + Phase 3: 图片提取）"""
        downloader = None
        if extract_images and download_images:
            downloader = ImageDownloader(
                base_path=image_path,
                quality=image_quality,
            )

        try:
            for i, ans in enumerate(answers):
                answer_id = ans.get("answer_id", "")
                title = ans.get("question_title", "")[:35]

                print(f"  [{i + 1}/{len(answers)}] {title}...")

                try:
                    # 调用 opencli zhihu answer-detail
                    detail = self.runner.zhihu_answer_detail(answer_id)

                    if detail:
                        # 转换为现有格式
                        converted = OpenCLIRunner.convert_answer_detail_to_legacy(
                            detail
                        )
                        if converted:
                            ans["content"] = converted.get("content", "")
                            ans["vote_count"] = converted.get("vote_count", 0)
                            ans["created_time"] = ans.get("created_time") or converted.get(
                                "created_time", ""
                            )
                            ans["author"] = converted.get("author", "")

                    # Phase 3: 图片提取（可选）
                    if extract_images and ans.get("content"):
                        answer_url = ans.get("question_url", "")
                        images = self._extract_images_from_answer(
                            answer_id, answer_url
                        )
                        if images:
                            ans["images"] = images

                            # 下载图片（ImageDownloader 是异步的，用 asyncio.run 包装）
                            if download_images and downloader:
                                print(f"      下载 {len(images)} 张图片...")
                                ans["images"] = asyncio.run(
                                    downloader.download_images(
                                        images,
                                        sub_dir=user_token,
                                        answer_id=answer_id,
                                    )
                                )
                                ans["content"] = downloader.insert_images_into_content(
                                    ans["content"],
                                    ans["images"],
                                )

                    # 进度提示
                    if (i + 1) % 10 == 0:
                        print(f"      >>> 已处理 {i + 1} 条")

                    time.sleep(1.5)

                except OpenCLIAuthError as e:
                    print(f"      认证错误: {e}")
                    print(f"      请先登录知乎: opencli browser zhihu init")
                    break
                except OpenCLITimeoutError as e:
                    print(f"      超时: {e}，重试中...")
                    try:
                        detail = self.runner.zhihu_answer_detail(answer_id)
                        if detail:
                            converted = (
                                OpenCLIRunner.convert_answer_detail_to_legacy(detail)
                            )
                            ans["content"] = converted.get("content", "")
                    except Exception:
                        print(f"      重试失败，跳过")
                except OpenCLIError as e:
                    print(f"      OpenCLI 错误: {e}")
                except Exception as e:
                    print(f"      错误: {type(e).__name__}: {e}")
        finally:
            pass  # ImageDownloader 上下文由 asyncio.run 管理

    def _extract_images_from_answer(
        self,
        answer_id: str,
        answer_url: str,
    ) -> List[Dict]:
        """通过 browser eval 从回答页提取图片 URL（Phase 3 辅助）

        OpenCLI 的 answer-detail 返回纯文本，不含 HTML 图片标签。
        需要额外调用 browser eval 提取 <img> 标签。

        Args:
            answer_id: 回答 ID（保留用于日志和未来扩展）
            answer_url: 回答页面 URL
        """
        if not answer_url:
            return []

        try:
            # 打开回答页面（answer_id 用于定位正确的回答链接）
            self.runner.browser_open(answer_url)
            self.runner.browser_wait("time", "2")

            js = """(function() {
                const images = [];
                document.querySelectorAll('.RichText img, .AnswerItem img, article img').forEach(function(img) {
                    let url = img.getAttribute('data-original') || img.src || '';
                    if (url && url.startsWith('//')) url = 'https:' + url;
                    if (url && (url.includes('zhimg.com') || url.startsWith('http'))) {
                        images.push({
                            url: url,
                            alt: img.alt || '',
                            width: img.width || 0,
                            height: img.height || 0
                        });
                    }
                });
                return images;
            })()"""

            result = self.runner.browser_eval(js)
            if isinstance(result, list):
                return result
            return []
        except OpenCLIError:
            return []

    def save_results(self, answers: List[Dict], output_file: str):
        """保存结果到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

        # 统计报告
        total = len(answers)
        if total == 0:
            return

        lengths = [len(a.get("content", "")) for a in answers]
        votes = [a.get("vote_count", 0) for a in answers]
        opencli_count = sum(
            1 for a in answers if a.get("source_backend") == "opencli"
        )

        report = f"""
============================================================
爬取报告 (OpenCLI)
============================================================

数据文件: {output_path.name}
后端: OpenCLI ({opencli_count}/{total} 条)

基本统计:
  总回答数: {total}
  内容长度: 最短 {min(lengths)} 字符, 最长 {max(lengths)} 字符, 平均 {int(sum(lengths) / len(lengths))} 字符
  总点赞数: {sum(votes)}
  平均点赞: {int(sum(votes) / len(votes)) if len(votes) > 0 else 0}

前5条回答:
"""
        sorted_by_votes = sorted(
            answers, key=lambda x: x.get("vote_count", 0), reverse=True
        )
        for i, ans in enumerate(sorted_by_votes[:5], 1):
            report += f"  {i}. [{ans.get('vote_count', 0)}赞] {ans.get('question_title', '')[:50]}...\n"

        report += "============================================================\n"
        print(report)

        # 保存报告
        report_file = output_path.with_suffix("").with_name(
            output_path.stem + "_报告.txt"
        )
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description="知乎用户回答爬虫 (OpenCLI 版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/crawl_user_opencli.py --user xu-ze-qiu
  python scripts/crawl_user_opencli.py --user xu-ze-qiu --count 50 --topic finance
  python scripts/crawl_user_opencli.py --user xu-ze-qiu --after-date 2026-03-01

前置条件:
  1. 安装 opencli: npm install -g opencli
  2. 初始化浏览器会话: opencli browser zhihu init
  3. 在打开的浏览器窗口中登录知乎

主题过滤:
  all        - 不过滤
  finance    - 金融/投资/股市
  tech       - 科技/AI
  international - 国际形势
  culture    - 动漫/电影/游戏
  life       - 生活/职场/情感
  自定义     - 自定义关键词
        """,
    )

    parser.add_argument("--user", type=str, required=True, help="用户 url_token")
    parser.add_argument("--count", type=int, default=100, help="爬取数量 (默认100)")
    parser.add_argument("--topic", type=str, default="all", help="主题过滤 (默认all)")
    parser.add_argument(
        "--after-date",
        type=str,
        default=None,
        help="爬取指定日期之后的回答 (格式: YYYY-MM-DD)",
    )
    parser.add_argument(
        "--before-date",
        type=str,
        default=None,
        help="爬取指定日期之前的回答 (格式: YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output", type=str, default="output/{user}_answers_opencli.json",
        help="输出文件"
    )
    parser.add_argument(
        "--no-content", action="store_true",
        help="不获取完整内容（只获取列表）"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="从断点继续爬取"
    )
    parser.add_argument(
        "--checkpoint-file",
        type=str,
        default="data/checkpoint.json",
        help="检查点文件路径",
    )
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
        help="图片质量 (默认hd)",
    )
    parser.add_argument(
        "--image-path",
        type=str,
        default="output/images",
        help="图片存储路径",
    )

    args = parser.parse_args()

    # 创建 runner
    runner = create_runner_from_config()

    # 检查点管理
    checkpoint = CheckpointManager(args.checkpoint_file)

    # 输出路径
    output_file = args.output.format(user=args.user)

    crawler = ZhihuUserCrawlerOpenCLI(runner=runner)

    try:
        answers = crawler.crawl_answers(
            user_token=args.user,
            count=args.count,
            topic=args.topic,
            after_date=args.after_date,
            before_date=args.before_date,
            with_content=not args.no_content,
            resume=args.resume,
            checkpoint=checkpoint,
            extract_images=not args.no_extract_images,
            download_images=not args.no_download_images,
            image_quality=args.image_quality,
            image_path=args.image_path,
        )

        crawler.save_results(answers, output_file)

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
