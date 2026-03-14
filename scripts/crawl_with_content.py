#!/usr/bin/env python3
"""
知乎回答内容爬取脚本 (简化版)
直接通过浏览器访问用户主页和回答页面获取完整内容

使用方法:
    python scripts/crawl_with_content.py --user 奥特之父
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from core.config import CRAWLER_CONFIG
from utils.checkpoint import CheckpointManager


class SimpleContentCrawler:
    """简化的知乎回答内容爬虫"""

    def __init__(self, auth_file: str = "data/zhihu_auth.json", headless: bool = False):
        self.auth_file = auth_file
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    async def init(self):
        """初始化浏览器"""
        playwright = await async_playwright().start()

        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
            ]
        )

        context_options = {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "viewport": {"width": 1920, "height": 1080},
        }

        auth_path = os.path.abspath(self.auth_file)
        if os.path.exists(auth_path):
            context_options["storage_state"] = auth_path

        self.context = await self.browser.new_context(**context_options)

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self.page = await self.context.new_page()

        # 访问知乎首页
        await self.page.goto("https://www.zhihu.com", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        print(f"  浏览器已启动")

    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()

    async def get_user_info(self, url_token: str):
        """获取用户信息"""
        try:
            # 访问用户主页
            user_url = f"https://www.zhihu.com/people/{url_token}"
            await self.page.goto(user_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 提取用户信息
            info = await self.page.evaluate("""() => {
                const name = document.querySelector('.ProfileHeader-name')?.innerText ||
                             document.querySelector('.name')?.innerText || '';

                const stats = document.querySelectorAll('.ProfileMain-itemValue');
                let answerCount = 0;
                stats.forEach(el => {
                    const text = el.innerText;
                    if (text.includes('回答')) {
                        answerCount = parseInt(text) || 0;
                    }
                });

                return { name, answerCount };
            }""")

            return info if info.get('name') else None

        except Exception as e:
            print(f"  获取用户信息失败: {e}")
            return None

    async def get_user_answers_from_page(self, url_token: str, offset: int = 0) -> tuple:
        """从用户回答页面获取回答列表"""

        # 访问用户的回答列表页面
        answers_url = f"https://www.zhihu.com/people/{url_token}/answers"
        await self.page.goto(answers_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 等待回答列表加载
        try:
            await self.page.wait_for_selector('.List-item', timeout=10000)
        except:
            pass

        # 提取回答数据
        answers_data = await self.page.evaluate("""(offset) => {
            const items = document.querySelectorAll('.List-item');
            const answers = [];

            items.forEach(item => {
                try {
                    const titleEl = item.querySelector('.ContentItem-title a') ||
                                   item.querySelector('.question-link') ||
                                   item.querySelector('a[href*="/question/"]');

                    const link = titleEl?.href || '';
                    const questionIdMatch = link.match(/\\/question\\/(\\d+)/);
                    const answerIdMatch = link.match(/\\/answer\\/(\\d+)/);

                    const title = titleEl?.innerText?.trim() || '';
                    const questionId = questionIdMatch ? questionIdMatch[1] : '';
                    const answerId = answerIdMatch ? answerIdMatch[1] : '';

                    const voteEl = item.querySelector('.VoteButton') ||
                                  item.querySelector('[class*="vote"]');
                    const voteup = voteEl?.getAttribute('aria-label') ||
                                  voteEl?.innerText || '0';
                    const voteCount = parseInt(voteup.replace(/[^0-9]/g, '')) || 0;

                    if (title && answerId) {
                        answers.push({
                            id: answerId,
                            question_id: questionId,
                            question_title: title,
                            url: link,
                            voteup_count: voteCount
                        });
                    }
                } catch (e) {}
            });

            return answers;
        }""", offset)

        # 检查是否还有更多
        has_more = len(answers_data) > 0

        return answers_data, has_more

    async def get_answer_content(self, answer_url: str) -> str:
        """获取单个回答的完整内容"""
        try:
            await self.page.goto(answer_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # 尝试提取回答内容
            content = await self.page.evaluate("""() => {
                // 尝试多种选择器
                const selectors = [
                    '.zm-item-answer .RichText',
                    '.AnswerItem .RichText',
                    '.Post-content',
                    '.answer-area .content',
                    '[itemprop="text"]',
                    '.qa-detail .content',
                    '.RichText'
                ];

                for (const selector of selectors) {
                    const el = document.querySelector((selector));
                    if (el && el.innerText.trim()) {
                        return el.innerText.trim();
                    }
                }

                // 返回整个回答区域的文本
                const answerEl = document.querySelector('.zm-item-answer');
                return answerEl ? answerEl.innerText : '';
            }""")

            return content if content else ""

        except Exception as e:
            print(f"    获取内容失败: {str(e)[:50]}")
            return ""

    async def crawl_user(
        self,
        url_token: str,
        user_name: str,
        expected_count: int = 0,
        output_dir: str = "output",
        resume: bool = True
    ):
        """爬取用户所有回答的完整内容"""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 检查点
        checkpoint = CheckpointManager(f"{output_dir}/checkpoint.json")

        # 恢复进度
        start_offset = 0
        if resume:
            progress = checkpoint.get(f"{user_name}_progress", {})
            start_offset = progress.get("offset", 0)

        print(f"\n开始爬取用户 '{user_name}' 的回答内容...")
        print(f"  起始偏移: {start_offset}")
        print("-" * 60)

        all_answers = []
        offset = start_offset

        # 获取回答列表（每页约20条）
        while True:
            print(f"\n[偏移 {offset}] 正在获取回答列表...")

            answers, has_more = await self.get_user_answers_from_page(url_token, offset)

            if not answers:
                print(f"  已到达末尾或无回答")
                break

            print(f"  获取到 {len(answers)} 条回答")

            # 获取每个回答的完整内容
            for i, answer in enumerate(answers):
                print(f"  [{offset + i + 1}] 获取内容: {answer['question_title'][:30]}...")

                content = await self.get_answer_content(answer['url'])
                answer['content'] = content

                # 格式化创建时间
                answer['created_time'] = int(datetime.now().timestamp())

                all_answers.append(answer)

                # 每10条保存一次
                if len(all_answers) >= 10:
                    self.save_answers(all_answers, output_path, user_name, offset)
                    all_answers = []

                # 请求间隔
                await asyncio.sleep(CRAWLER_CONFIG["request_delay"])

            offset += len(answers)

            # 更新检查点
            checkpoint.set(f"{user_name}_progress", {
                "offset": offset,
                "collected": offset,
                "timestamp": datetime.now().isoformat()
            })

            print(f"  ✓ 已处理: {offset} 条")

            # 检查是否完成
            if expected_count > 0 and offset >= expected_count:
                break

            if not has_more:
                break

        # 保存剩余数据
        if all_answers:
            self.save_answers(all_answers, output_path, user_name, offset)

        # 合并所有数据
        all_data = []
        for f in sorted(output_path.glob(f"{user_name}_answers_content_*.json")):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    all_data.extend(json.load(fp))
            except:
                pass

        # 保存完整文件
        full_output = output_path / f"{user_name}_answers_full.json"
        with open(full_output, 'w', encoding='utf-8') as fp:
            json.dump(all_data, fp, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"爬取完成!")
        print(f"  总计: {len(all_data)} 条回答")
        print(f"  输出: {full_output}")
        print(f"{'='*60}")

        return len(all_data)

    def save_answers(self, answers, output_path, user_name, offset):
        """保存回答数据"""
        filename = output_path / f"{user_name}_answers_content_{offset}.json"
        with open(filename, 'w', encoding='utf-8') as fp:
            json.dump(answers, fp, ensure_ascii=False, indent=2)
        print(f"    [保存] {len(answers)} 条到 {filename.name}")


async def main():
    parser = argparse.ArgumentParser(description="知乎回答内容爬取工具")
    parser.add_argument("--user", type=str, required=True, help="知乎用户ID (url_token)")
    parser.add_argument("--output", type=str, default="output", help="输出目录")
    parser.add_argument("--count", type=int, default=0, help="预期回答数量")
    parser.add_argument("--headless", action="store_true", default=False, help="无头模式")
    parser.add_argument("--no-resume", action="store_true", help="不恢复检查点")

    args = parser.parse_args()

    user_id = args.user

    # 创建爬虫
    crawler = SimpleContentCrawler(headless=args.headless)

    try:
        await crawler.init()

        # 获取用户信息
        print(f"\n正在获取用户 '{user_id}' 的信息...")
        user_info = await crawler.get_user_info(user_id)

        if user_info:
            print(f"  用户名: {user_info.get('name', 'N/A')}")
            print(f"  回答数: {user_info.get('answerCount', 'N/A')}")
            expected = args.count or user_info.get('answerCount', 0)
        else:
            print(f"  无法获取用户信息，将尝试直接爬取")
            expected = args.count

        # 开始爬取
        await crawler.crawl_user(
            url_token=user_id,
            user_name=user_id,
            expected_count=expected,
            output_dir=args.output,
            resume=not args.no_resume
        )

    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())