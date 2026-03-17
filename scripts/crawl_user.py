#!/usr/bin/env python3
"""
知乎用户回答爬虫 - 支持多种过滤和数量控制

用法:
    # 爬取用户所有回答
    python scripts/crawl_user.py --user xu-ze-qiu

    # 爬取指定数量
    python scripts/crawl_user.py --user xu-ze-qiu --count 100

    # 按主题过滤（金融/投资/股市相关）
    python scripts/crawl_user.py --user xu-ze-qiu --count 100 --topic finance

    # 按日期筛选（爬取指定日期之后的回答）
    python scripts/crawl_user.py --user xu-ze-qiu --after-date 2026-03-01

    # 组合使用：日期 + 主题 + 数量
    python scripts/crawl_user.py --user xu-ze-qiu --count 50 --topic finance --after-date 2026-01-01

    # 组合使用
    python scripts/crawl_user.py --user xu-ze-qiu --count 100 --topic finance --output data.json
"""

import asyncio
import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.browser import BrowserManager
from utils.checkpoint import CheckpointManager


@dataclass
class CrawlerConfig:
    """爬虫配置"""

    auth_file: str = "data/zhihu_auth.json"
    headless: bool = True
    request_delay: float = 2.0
    timeout: int = 60000



# ============ 主题关键词 ============

TOPIC_KEYWORDS = {
    "finance": [
        "A股",
        "股市",
        "股票",
        "大盘",
        "涨停",
        "跌停",
        "牛市",
        "熊市",
        "抄底",
        "基金",
        "投资",
        "理财",
        "金融",
        "沪指",
        "创业板",
        "光伏",
        "宁德",
        "比亚迪",
        "小米",
        "英伟达",
        "格力",
        "蔚来",
        "智界",
        "油价",
        "石油",
        "黄金",
        "美元",
        "人民币",
        "汇率",
        "国债",
        "债市",
        "期货",
        "期权",
        "量化",
        "私募",
        "公募",
        "IPO",
        "转债",
        "融券",
        "融资",
        "配股",
        "分红",
        "股息",
    ],
    "tech": [
        "AI",
        "人工智能",
        "大模型",
        "ChatGPT",
        "GPT",
        "Claude",
        "芯片",
        "半导体",
        "CPU",
        "GPU",
        "英伟达",
        "AMD",
        "英特尔",
        "手机",
        "华为",
        "苹果",
        "小米",
        "OPPO",
        "vivo",
        "三星",
        "新能源",
        "电动车",
        "特斯拉",
        "比亚迪",
        "自动驾驶",
        "智驾",
        "机器人",
        "具身智能",
        "人形机器人",
        "宇树",
        "特斯拉",
    ],
    "international": [
        "伊朗",
        "以色列",
        "中东",
        "霍尔木兹",
        "美军",
        "战争",
        "哈梅内伊",
        "美国",
        "特朗普",
        "拜登",
        "普京",
        "俄罗斯",
        "乌克兰",
        "日本",
        "韩国",
        "朝鲜",
        "台海",
        "南海",
        "中美",
        "G7",
    ],
    "culture": [
        "动漫",
        "漫画",
        "龙珠",
        "JoJo",
        "鸟山明",
        "镖人",
        "电影",
        "票房",
        "春节档",
        "热辣滚烫",
        "飞驰人生",
        "音乐",
        "游戏",
        "主播",
        "直播",
        "短视频",
    ],
    "life": [
        "买房",
        "房价",
        "房子",
        "别墅",
        "装修",
        "房贷",
        "工作",
        "职场",
        "创业",
        "裁员",
        "就业",
        "工资",
        "恋爱",
        "婚姻",
        "相亲",
        "出轨",
        "老婆",
        "老公",
    ],
}


# ============ 爬虫类 ============


class ZhihuCrawler:
    """知乎爬虫"""

    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.config = config or CrawlerConfig()
        self.browser_manager: Optional[BrowserManager] = None
        self.page = None

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def init(self):
        """初始化浏览器"""
        self.browser_manager = BrowserManager(
            auth_file=self.config.auth_file,
            headless=self.config.headless,
            timeout=self.config.timeout,
        )
        await self.browser_manager.init()
        self.page = self.browser_manager.page

    async def close(self):
        """关闭浏览器"""
        if self.browser_manager:
            await self.browser_manager.close()

    def check_topic(self, text: str, topic: str) -> bool:
        """检查文本是否匹配指定主题"""
        if topic == "all":
            return True

        keywords = TOPIC_KEYWORDS.get(topic, [])
        if not keywords:
            # 如果不是预定义主题，直接用关键词匹配
            return topic.lower() in text.lower()

        return any(kw in text for kw in keywords)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析多种格式的日期字符串"""
        if not date_str:
            return None

        # 1. ISO 格式 (从 <meta> 或 <time datetime="..."> 获取)
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y年%m月%d日",
        ]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # 2. 相对时间: "x 小时前"、"x 天前"、"昨天"、"前天"
        now = datetime.now()

        hours_match = re.search(r"(\d+)\s*小时前", date_str)
        if hours_match:
            return now - timedelta(hours=int(hours_match.group(1)))

        days_match = re.search(r"(\d+)\s*天前", date_str)
        if days_match:
            return now - timedelta(days=int(days_match.group(1)))

        if "昨天" in date_str:
            return now - timedelta(days=1)

        if "前天" in date_str:
            return now - timedelta(days=2)

        # 3. 从文本中提取嵌入的日期 ("发布于 2026-03-15")
        embedded = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
        if embedded:
            try:
                return datetime.strptime(embedded.group(1), "%Y-%m-%d")
            except ValueError:
                pass

        return None

    async def get_user_info(self, user_token: str) -> Dict:
        """获取用户信息"""
        user_url = f"https://www.zhihu.com/people/{user_token}"
        await self.page.goto(user_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        info = await self.page.evaluate("""() => {
            const nameEl = document.querySelector('.ProfileHeader-name, .name, h1');
            const tabs = document.querySelectorAll('.Tabs-tab');

            let answerCount = 0;
            tabs.forEach(tab => {
                const text = tab.innerText;
                const match = text.match(/回答[\s:]*(\d+)/);
                if (match) answerCount = parseInt(match[1]);
            });

            return {
                name: nameEl ? nameEl.innerText.trim() : '',
                answerCount: answerCount,
                url: window.location.href
            };
        }""")

        return info

    async def crawl_answers(
        self,
        user_token: str,
        count: int = 100,
        topic: str = "all",
        after_date: str = None,
        before_date: str = None,
        with_content: bool = True,
        resume: bool = False,
        checkpoint=None,
    ) -> List[Dict]:
        """
        爬取用户回答

        Args:
            user_token: 用户url_token
            count: 目标数量
            topic: 主题过滤 (all/finance/tech/international/culture/life 或自定义关键词)
            after_date: 爬取指定日期之后的回答 (格式: YYYY-MM-DD)
            before_date: 爬取指定日期之前的回答 (格式: YYYY-MM-DD)
            with_content: 是否获取完整内容
            resume: 是否从断点继续
            checkpoint: CheckpointManager实例
        """
        # 初始化变量
        all_answers = []
        scroll_count = 0

        # 检查点恢复
        if resume and checkpoint:
            saved_progress = checkpoint.get(f"{user_token}_progress", {})
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

        # 访问用户回答页面
        answers_url = f"https://www.zhihu.com/people/{user_token}/answers"
        await self.page.goto(answers_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        print(f"\n开始爬取用户 {user_token} 的回答...")
        print(f"  目标数量: {count}")
        print(f"  主题过滤: {topic}")
        if after_date:
            print(f"  日期筛选: {after_date} 之后")
        if before_date:
            print(f"  日期筛选: {before_date} 之前")
        print("-" * 50)

        # 每次滚动约加载 20 条，根据目标数量动态计算上限
        max_scrolls = max(30, (count // 10) + 5)
        no_new_count = 0  # 连续无新内容的滚动次数

        while len(all_answers) < count and scroll_count < max_scrolls:
            # 获取当前页面回答（包含日期信息）
            answers = await self.page.evaluate(
                """(existingIds) => {
                const results = [];
                const items = document.querySelectorAll('.List-item, .ContentItem');

                items.forEach(item => {
                    try {
                        const link = item.querySelector('a[href*="/question/"][href*="/answer/"]');
                        if (!link) return;

                        const title = link.innerText.trim();
                        const href = link.href;

                        const qMatch = href.match(/\/question\/(\d+)/);
                        const aMatch = href.match(/\/answer\/(\d+)/);

                        if (!qMatch || !aMatch) return;

                        const questionId = qMatch[1];
                        const answerId = aMatch[1];

                        // 尝试获取日期 - 优先从 <meta> 或 <time> 的 datetime 属性获取
                        let createdTime = '';
                        // 1. 尝试 <meta itemprop="dateCreated">
                        const metaDate = item.querySelector('meta[itemprop="dateCreated"]');
                        if (metaDate) {
                            createdTime = metaDate.getAttribute('content') || '';
                        }
                        // 2. 尝试 <time> 元素的 datetime 属性
                        if (!createdTime) {
                            const timeEl = item.querySelector('time[datetime]');
                            if (timeEl) {
                                createdTime = timeEl.getAttribute('datetime') || '';
                            }
                        }
                        // 3. 从文本中提取日期（"发布于 2026-03-15"、"编辑于 2026-03-15"）
                        if (!createdTime) {
                            const timeTextEl = item.querySelector('.ContentItem-time, [class*="time"], [class*="date"]');
                            if (timeTextEl) {
                                const text = timeTextEl.innerText.trim();
                                const dateMatch = text.match(/(\d{4}-\d{2}-\d{2})/);
                                if (dateMatch) {
                                    createdTime = dateMatch[1];
                                } else {
                                    // 处理 "x 小时前"、"昨天" 等相对时间
                                    createdTime = text;
                                }
                            }
                        }

                        if (!existingIds.includes(answerId)) {
                            results.push({
                                question_title: title,
                                question_url: href,
                                question_id: questionId,
                                answer_id: answerId,
                                created_time: createdTime,
                                content: '',
                                vote_count: 0
                            });
                        }
                    } catch (e) {}
                });

                return results;
            }""",
                [a["answer_id"] for a in all_answers],
            )

            # 过滤主题、日期并去重
            existing_ids = set(a["answer_id"] for a in all_answers)
            for ans in answers:
                if ans["answer_id"] in existing_ids:
                    continue

                # 检查主题
                text = ans["question_title"]
                if not self.check_topic(text, topic):
                    continue

                # 检查日期
                if after_dt or before_dt:
                    created = ans.get("created_time", "")
                    if created:
                        answer_dt = self._parse_date(created)
                        if answer_dt:
                            if after_dt and answer_dt < after_dt:
                                continue
                            if before_dt and answer_dt > before_dt:
                                continue

                all_answers.append(ans)
                existing_ids.add(ans["answer_id"])

            prev_count = len(all_answers)
            scroll_count += 1
            print(f"  滚动 {scroll_count}: 共 {len(all_answers)} 条匹配的回答")

            if len(all_answers) >= count:
                break

            # 连续 5 次滚动无新内容，说明已到底部
            if len(all_answers) == prev_count:
                no_new_count += 1
                if no_new_count >= 5:
                    print(f"  连续 {no_new_count} 次无新内容，停止滚动")
                    break
            else:
                no_new_count = 0

            # 滚动加载更多
            await self.page.evaluate("window.scrollBy(0, 1200);")
            await asyncio.sleep(2)

        # 限制数量
        all_answers = all_answers[:count]

        # 保存检查点
        if checkpoint:
            checkpoint.set(
                f"{user_token}_progress",
                {
                    "scroll_count": scroll_count,
                    "answers": all_answers,
                    "timestamp": datetime.now().isoformat(),
                },
            )

        # 获取完整内容
        if with_content:
            print(f"\n获取完整内容 ({len(all_answers)} 条)...")
            await self._fetch_content(all_answers)

        print(f"\n✓ 完成! 共获取 {len(all_answers)} 条回答")

        return all_answers

    async def _fetch_content(self, answers: List[Dict]):
        """获取回答完整内容"""
        for i, ans in enumerate(answers):
            url = ans.get("question_url", "")
            title = ans.get("question_title", "")[:35]

            print(f"  [{i + 1}/{len(answers)}] {title}...")

            try:
                await self.page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                content = await self.page.evaluate("""() => {
                    let el = document.querySelector('.zm-item-answer .RichText');
                    if (el) return el.innerText.trim();

                    el = document.querySelector('.AnswerItem .RichText');
                    if (el) return el.innerText.trim();

                    return '';
                }""")

                if content:
                    ans["content"] = content

                # 每10条保存一次
                if (i + 1) % 10 == 0:
                    print(f"      >>> 已处理 {i + 1} 条")

                await asyncio.sleep(1.5)

            except Exception as e:
                print(f"      错误: {type(e).__name__}: {e}")

    def save_results(self, answers: List[Dict], output_file: str):
        """保存结果到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

        # 生成统计报告
        self.generate_report(answers, output_path)

    def generate_report(self, answers: List[Dict], output_path: Path):
        """生成统计报告"""
        total = len(answers)
        if total == 0:
            return

        lengths = [len(a.get("content", "")) for a in answers]
        votes = [a.get("vote_count", 0) for a in answers]

        report = f"""
============================================================
爬取报告
============================================================

数据文件: {output_path.name}

基本统计:
  总回答数: {total}
  内容长度: 最短 {min(lengths)} 字符, 最长 {max(lengths)} 字符, 平均 {int(sum(lengths) / len(lengths))} 字符
  总点赞数: {sum(votes)}
  平均点赞: {int(sum(votes) / len(votes))}

前5条回答:
"""

        sorted_by_votes = sorted(
            answers, key=lambda x: x.get("vote_count", 0), reverse=True
        )
        for i, ans in enumerate(sorted_by_votes[:5], 1):
            report += f"  {i}. [{ans.get('vote_count', 0)}赞] {ans['question_title'][:50]}...\n"

        report += "============================================================\n"

        print(report)

        # 保存报告
        report_file = output_path.with_suffix("").with_name(
            output_path.stem + "_报告.txt"
        )
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)


# ============ 主函数 ============


async def main():
    parser = argparse.ArgumentParser(
        description="知乎用户回答爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/crawl_user.py --user xu-ze-qiu
  python scripts/crawl_user.py --user xu-ze-qiu --count 100 --topic finance
  python scripts/crawl_user.py --user xu-ze-qiu --topic A股 --count 50 --output my_data.json

主题过滤:
  all        - 不过滤，获取所有回答
  finance    - 金融/投资/股市相关
  tech       - 科技/AI/手机相关
  international - 国际形势相关
  culture    - 动漫/电影/游戏相关
  life       - 生活/职场/情感相关
  自定义     - 使用自定义关键词过滤
        """,
    )

    parser.add_argument("--user", type=str, required=True, help="用户url_token")
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
        "--output", type=str, default="output/{user}_answers.json", help="输出文件"
    )
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument(
        "--no-content", action="store_true", help="不获取完整内容（只获取列表）"
    )
    parser.add_argument("--resume", action="store_true", help="从断点继续爬取")
    parser.add_argument(
        "--checkpoint-file",
        type=str,
        default="data/checkpoint.json",
        help="检查点文件路径",
    )

    args = parser.parse_args()

    # 配置
    config = CrawlerConfig(headless=args.headless)

    # 检查点管理
    checkpoint = CheckpointManager(args.checkpoint_file)

    # 处理输出路径
    output_file = args.output.format(user=args.user)
    if output_file == "output/{user}_answers.json":
        output_file = f"output/{args.user}_answers.json"

    async with ZhihuCrawler(config) as crawler:
        # 获取用户信息
        user_info = await crawler.get_user_info(args.user)
        print(f"\n用户: {user_info.get('name', args.user)}")
        print(f"回答数: {user_info.get('answerCount', 'N/A')}")

        # 爬取回答
        answers = await crawler.crawl_answers(
            user_token=args.user,
            count=args.count,
            topic=args.topic,
            after_date=args.after_date,
            before_date=args.before_date,
            with_content=not args.no_content,
            resume=args.resume,
            checkpoint=checkpoint,
        )

        # 保存结果
        crawler.save_results(answers, output_file)


if __name__ == "__main__":
    asyncio.run(main())
