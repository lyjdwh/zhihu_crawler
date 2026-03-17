"""
知乎 API 封装模块
提供知乎数据获取的核心功能
"""

import asyncio
import random
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from playwright.async_api import Page

from core.browser import BrowserManager
from core.config import ZHIHU_CONFIG, CRAWLER_CONFIG


@dataclass
class ZhihuUser:
    """知乎用户信息"""

    id: str
    name: str
    url_token: str
    answer_count: int = 0
    article_count: int = 0
    follower_count: int = 0


@dataclass
class ZhihuAnswer:
    """知乎回答数据"""

    id: str
    type: str = "answer"
    question: Optional[Dict[str, Any]] = None
    content: str = ""
    voteup_count: int = 0
    comment_count: int = 0
    created_time: int = 0
    url: str = ""


class ZhihuAPI:
    """知乎 API 客户端"""

    def __init__(
        self,
        auth_file: str = "data/zhihu_auth.json",
        headless: bool = True,
        request_delay: float = 2.0,
    ):
        self.auth_file = auth_file
        self.headless = headless
        self.request_delay = request_delay

        self.browser_manager: Optional[BrowserManager] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def init(self):
        """初始化浏览器"""
        self.browser_manager = BrowserManager(
            auth_file=self.auth_file,
            headless=self.headless,
        )
        await self.browser_manager.init()
        self.page = self.browser_manager.page

    async def close(self):
        """关闭浏览器"""
        if self.browser_manager:
            await self.browser_manager.close()

    async def _api_request(self, url: str, max_retries: int = 5) -> Optional[Dict]:
        """发送 API 请求"""
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = 3 + random.random() * 2
                    print(f"  等待 {delay:.1f}s 后重试...")
                    await asyncio.sleep(delay)

                # 使用 page.evaluate 在浏览器环境中发起请求
                result = await self.page.evaluate(
                    """async (targetUrl) => {
                    try {
                        const response = await fetch(targetUrl, {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'accept': 'application/json, text/plain, */*',
                                'x-requested-with': 'fetch',
                                'x-zse-93': '101_3_3.0',
                                'x-zse-96': ''
                            }
                        });

                        if (!response.ok) {
                            return {
                                success: false,
                                status: response.status,
                                statusText: response.statusText
                            };
                        }

                        const data = await response.json();
                        return { success: true, data };
                    } catch (err) {
                        return { success: false, error: err.message };
                    }
                }""",
                    url,
                )

                if result.get("success"):
                    return result.get("data")
                else:
                    error_msg = f"HTTP {result.get('status', 'unknown')}: {result.get('statusText', result.get('error', 'unknown error'))}"
                    print(f"  请求失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")

            except Exception as e:
                print(f"  请求异常 (尝试 {attempt + 1}/{max_retries}): {str(e)}")

        return None

    async def get_user_info(self, url_token: str) -> Optional[ZhihuUser]:
        """获取用户信息"""
        url = f"{ZHIHU_CONFIG['api_url']}/members/{url_token}?include=id,name,answer_count,articles_count,follower_count"

        data = await self._api_request(url)
        if not data:
            return None

        return ZhihuUser(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            url_token=url_token,
            answer_count=data.get("answer_count", 0),
            article_count=data.get("articles_count", 0),
            follower_count=data.get("follower_count", 0),
        )

    async def get_answers(
        self, user_id: str, offset: int = 0, limit: int = 20
    ) -> Tuple[List[ZhihuAnswer], bool]:
        """获取用户回答列表"""
        url = f"{ZHIHU_CONFIG['api_url']}/members/{user_id}/answers?include=data[*].content,voteup_count,comment_count,created_time,question&offset={offset}&limit={limit}&sort_by=created"

        data = await self._api_request(url)
        if not data or not isinstance(data, dict):
            return [], False

        answers_data = data.get("data", [])
        paging = data.get("paging", {})
        is_end = paging.get("is_end", True)

        answers = []
        for item in answers_data:
            question_data = item.get("question", {})
            answer = ZhihuAnswer(
                id=str(item.get("id", "")),
                type="answer",
                question={
                    "id": str(question_data.get("id", "")),
                    "title": question_data.get("title", ""),
                }
                if question_data
                else None,
                content=item.get("content", ""),
                voteup_count=item.get("voteup_count", 0),
                comment_count=item.get("comment_count", 0),
                created_time=item.get("created_time", 0),
                url=f"https://www.zhihu.com/question/{question_data.get('id', '')}/answer/{item.get('id', '')}"
                if question_data
                else "",
            )
            answers.append(answer)

        return answers, not is_end

    async def crawl_all_answers(
        self,
        user_id: str,
        user_name: str,
        expected_count: int = 0,
        checkpoint_manager=None,
        storage=None,
        progress_callback=None,
    ):
        """爬取用户所有回答"""
        offset = 0
        total_collected = 0
        batch_size = 20
        has_more = True

        # 从检查点恢复进度
        if checkpoint_manager:
            progress = checkpoint_manager.get(f"{user_name}_progress", {})
            offset = progress.get("offset", 0)
            total_collected = progress.get("collected", 0)
            print(f"  从检查点恢复: 已收集 {total_collected} 条，偏移量 {offset}")

        while has_more:
            answers, has_more = await self.get_answers(user_id, offset, batch_size)

            if not answers:
                print(f"  警告: 未获取到数据，可能已到达末尾")
                break

            # 保存数据
            if storage:
                for answer in answers:
                    storage.add(answer.__dict__)

            total_collected += len(answers)
            offset += len(answers)

            # 更新检查点
            if checkpoint_manager:
                checkpoint_manager.set(
                    f"{user_name}_progress",
                    {
                        "offset": offset,
                        "collected": total_collected,
                        "timestamp": datetime.now().isoformat(),
                    },
                )

            # 进度回调
            if progress_callback:
                progress_callback(total_collected, expected_count)

            print(f"  ✓ 已获取: {total_collected} 条回答 (偏移量: {offset})")

            # 检查是否已达到预期数量
            if expected_count > 0 and total_collected >= expected_count:
                print(f"  已达到预期总数 {expected_count}，结束爬取")
                break

            # 请求间隔
            await asyncio.sleep(CRAWLER_CONFIG["request_delay"])

        # 关闭存储
        if storage:
            stats = storage.close()
            print(
                f"\n  数据保存完成: {stats['total_saved']} 条，{stats['batch_count']} 个文件"
            )

        return total_collected
