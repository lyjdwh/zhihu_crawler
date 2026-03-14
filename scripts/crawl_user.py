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

    # 组合使用
    python scripts/crawl_user.py --user xu-ze-qiu --count 100 --topic finance --output data.json
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from collections import Counter

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


# ============ 配置 ============

@dataclass
class CrawlerConfig:
    """爬虫配置"""
    auth_file: str = "data/zhihu_auth.json"
    headless: bool = False
    request_delay: float = 2.0
    timeout: int = 60000


@dataclass
class Answer:
    """回答数据结构"""
    question_title: str
    question_url: str
    answer_id: str
    question_id: str
    content: str
    vote_count: int
    created_time: Optional[str] = None


# ============ 主题关键词 ============

TOPIC_KEYWORDS = {
    "finance": [
        "A股", "股市", "股票", "大盘", "涨停", "跌停", "牛市", "熊市",
        "抄底", "基金", "投资", "理财", "金融", "沪指", "创业板",
        "光伏", "宁德", "比亚迪", "小米", "英伟达", "格力", "蔚来",
        "智界", "油价", "石油", "黄金", "美元", "人民币", "汇率",
        "国债", "债市", "期货", "期权", "量化", "私募", "公募",
        "IPO", "转债", "融券", "融资", "配股", "分红", "股息"
    ],
    "tech": [
        "AI", "人工智能", "大模型", "ChatGPT", "GPT", "Claude",
        "芯片", "半导体", "CPU", "GPU", "英伟达", "AMD", "英特尔",
        "手机", "华为", "苹果", "小米", "OPPO", "vivo", "三星",
        "新能源", "电动车", "特斯拉", "比亚迪", "自动驾驶", "智驾",
        "机器人", "具身智能", "人形机器人", "宇树", "特斯拉"
    ],
    "international": [
        "伊朗", "以色列", "中东", "霍尔木兹", "美军", "战争", "哈梅内伊",
        "美国", "特朗普", "拜登", "普京", "俄罗斯", "乌克兰",
        "日本", "韩国", "朝鲜", "台海", "南海", "中美", "G7"
    ],
    "culture": [
        "动漫", "漫画", "龙珠", "JoJo", "鸟山明", "镖人",
        "电影", "票房", "春节档", "热辣滚烫", "飞驰人生",
        "音乐", "游戏", "主播", "直播", "短视频"
    ],
    "life": [
        "买房", "房价", "房子", "别墅", "装修", "房贷",
        "工作", "职场", "创业", "裁员", "就业", "工资",
        "恋爱", "婚姻", "相亲", "出轨", "老婆", "老公"
    ]
}


# ============ 爬虫类 ============

class ZhihuCrawler:
    """知乎爬虫"""

    def __init__(self, config: CrawlerConfig = None):
        self.config = config or CrawlerConfig()
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self):
        await self.init()
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def init(self):
        """初始化浏览器"""
        playwright = await async_playwright().start()

        self.browser = await playwright.chromium.launch(
            headless=self.config.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ]
        )

        context_options = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
        }

        auth_path = os.path.abspath(self.config.auth_file)
        if os.path.exists(auth_path):
            context_options["storage_state"] = auth_path

        self.context = await self.browser.new_context(**context_options)

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """)

        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.config.timeout)

        # 访问知乎首页
        await self.page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()

    def check_topic(self, text: str, topic: str) -> bool:
        """检查文本是否匹配指定主题"""
        if topic == "all":
            return True

        keywords = TOPIC_KEYWORDS.get(topic, [])
        if not keywords:
            # 如果不是预定义主题，直接用关键词匹配
            return topic.lower() in text.lower()

        return any(kw in text for kw in keywords)

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
        with_content: bool = True
    ) -> List[Dict]:
        """
        爬取用户回答

        Args:
            user_token: 用户url_token
            count: 目标数量
            topic: 主题过滤 (all/finance/tech/international/culture/life 或自定义关键词)
            with_content: 是否获取完整内容
        """
        # 访问用户回答页面
        answers_url = f"https://www.zhihu.com/people/{user_token}/answers"
        await self.page.goto(answers_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        print(f"\n开始爬取用户 {user_token} 的回答...")
        print(f"  目标数量: {count}")
        print(f"  主题过滤: {topic}")
        print("-" * 50)

        all_answers = []
        scroll_count = 0
        max_scrolls = 30

        while len(all_answers) < count and scroll_count < max_scrolls:
            # 获取当前页面回答
            answers = await self.page.evaluate("""(existingIds) => {
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

                        if (!existingIds.includes(answerId)) {
                            results.push({
                                question_title: title,
                                question_url: href,
                                question_id: questionId,
                                answer_id: answerId,
                                content: '',
                                vote_count: 0
                            });
                        }
                    } catch (e) {}
                });

                return results;
            }""", [a['answer_id'] for a in all_answers])

            # 过滤主题并去重
            existing_ids = set(a['answer_id'] for a in all_answers)
            for ans in answers:
                if ans['answer_id'] in existing_ids:
                    continue

                # 检查主题
                text = ans['question_title']
                if not self.check_topic(text, topic):
                    continue

                all_answers.append(ans)
                existing_ids.add(ans['answer_id'])

            scroll_count += 1
            print(f"  滚动 {scroll_count}: 共 {len(all_answers)} 条匹配的回答")

            if len(all_answers) >= count:
                break

            # 滚动加载更多
            await self.page.evaluate("window.scrollBy(0, 1200);")
            await asyncio.sleep(2)

        # 限制数量
        all_answers = all_answers[:count]

        # 获取完整内容
        if with_content:
            print(f"\n获取完整内容 ({len(all_answers)} 条)...")
            await self._fetch_content(all_answers)

        print(f"\n✓ 完成! 共获取 {len(all_answers)} 条回答")

        return all_answers

    async def _fetch_content(self, answers: List[Dict]):
        """获取回答完整内容"""
        for i, ans in enumerate(answers):
            url = ans.get('question_url', '')
            title = ans.get('question_title', '')[:35]

            print(f"  [{i+1}/{len(answers)}] {title}...")

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
                    ans['content'] = content

                # 每10条保存一次
                if (i + 1) % 10 == 0:
                    print(f"      >>> 已处理 {i+1} 条")

                await asyncio.sleep(1.5)

            except Exception as e:
                print(f"      错误: {str(e)[:30]}")

    def save_results(self, answers: List[Dict], output_file: str):
        """保存结果到文件"""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(answers, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

        # 生成统计报告
        self.generate_report(answers, output_path)

    def generate_report(self, answers: List[Dict], output_path: Path):
        """生成统计报告"""
        total = len(answers)
        if total == 0:
            return

        lengths = [len(a.get('content', '')) for a in answers]
        votes = [a.get('vote_count', 0) for a in answers]

        report = f"""
============================================================
爬取报告
============================================================

数据文件: {output_path.name}

基本统计:
  总回答数: {total}
  内容长度: 最短 {min(lengths)} 字符, 最长 {max(lengths)} 字符, 平均 {int(sum(lengths)/len(lengths))} 字符
  总点赞数: {sum(votes)}
  平均点赞: {int(sum(votes)/len(votes))}

前5条回答:
"""

        sorted_by_votes = sorted(answers, key=lambda x: x.get('vote_count', 0), reverse=True)
        for i, ans in enumerate(sorted_by_votes[:5], 1):
            report += f"  {i}. [{ans.get('vote_count', 0)}赞] {ans['question_title'][:50]}...\n"

        report += "============================================================\n"

        print(report)

        # 保存报告
        report_file = output_path.with_suffix('').with_name(output_path.stem + '_报告.txt')
        with open(report_file, 'w', encoding='utf-8') as f:
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
        """
    )

    parser.add_argument("--user", type=str, required=True, help="用户url_token")
    parser.add_argument("--count", type=int, default=100, help="爬取数量 (默认100)")
    parser.add_argument("--topic", type=str, default="all", help="主题过滤 (默认all)")
    parser.add_argument("--output", type=str, default="output/{user}_answers.json", help="输出文件")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--no-content", action="store_true", help="不获取完整内容（只获取列表）")

    args = parser.parse_args()

    # 配置
    config = CrawlerConfig(
        headless=args.headless
    )

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
            with_content=not args.no_content
        )

        # 保存结果
        crawler.save_results(answers, output_file)


if __name__ == "__main__":
    asyncio.run(main())