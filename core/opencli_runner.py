"""
OpenCLI 运行器模块 - 封装 opencli 子进程调用

通过 subprocess 调用 opencli CLI，利用其浏览器桥接功能获取知乎数据。
无需维护 Playwright 代码、auth storage 等。

用法:
    runner = OpenCLIRunner()
    hot = runner.zhihu_hot(limit=10)
    detail = runner.zhihu_answer_detail("12345678")
"""

import json
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


# ============ 异常类 ============

class OpenCLIError(Exception):
    """OpenCLI 通用错误"""
    pass


class OpenCLINotFoundError(OpenCLIError):
    """opencli 可执行文件未找到"""
    pass


class OpenCLIAuthError(OpenCLIError):
    """认证失败 / 浏览器未连接"""
    pass


class OpenCLITimeoutError(OpenCLIError):
    """子进程超时"""
    pass


class OpenCLIOutputError(OpenCLIError):
    """JSON 输出解析失败"""
    pass


# ============ 配置 ============

@dataclass
class OpenCLIConfig:
    """OpenCLI 运行器配置

    所有字段均有默认值，可通过项目 config 模块覆盖。
    """
    binary_path: str = "opencli"
    browser_session: str = "zhihu"
    window_mode: str = "background"    # foreground / background
    site_session: str = "persistent"   # ephemeral / persistent
    timeout: int = 120                 # 子进程超时（秒）
    request_delay: float = 2.0         # 请求间隔（秒）
    output_format: str = "json"
    extra_args: List[str] = field(default_factory=list)


# ============ 运行器核心 ============

class OpenCLIRunner:
    """OpenCLI 运行器 - 封装所有 opencli 子进程调用"""

    def __init__(self, config: Optional[OpenCLIConfig] = None):
        """
        Args:
            config: OpenCLI 配置，为 None 时使用默认配置
        """
        self.config = config or OpenCLIConfig()
        self._last_request_time: float = 0.0

    # ---------- 内部方法 ----------

    def _build_base_args(self) -> List[str]:
        """构建共享的 opencli 基础参数"""
        args = [self.config.binary_path]
        # browser 通用参数
        if self.config.window_mode:
            args.extend(["--window", self.config.window_mode])
        if self.config.site_session:
            args.extend(["--site-session", self.config.site_session])
        args.extend(self.config.extra_args)
        return args

    def _rate_limit(self):
        """请求频率控制"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.request_delay:
            time.sleep(self.config.request_delay - elapsed)
        self._last_request_time = time.time()

    def _run(
        self,
        args: List[str],
        timeout: Optional[int] = None,
        check_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """执行 opencli 命令（返回 CompletedProcess）

        Args:
            args: 命令行参数列表（不含 opencli 本身）
            timeout: 超时时间，默认使用配置值
            check_output: 是否解析并检查 stderr 错误

        Returns:
            subprocess.CompletedProcess

        Raises:
            OpenCLINotFoundError: opencli 未安装
            OpenCLIAuthError: 认证/登录问题
            OpenCLITimeoutError: 超时
            OpenCLIError: 其他错误
        """
        self._rate_limit()

        cmd = [self.config.binary_path] + args
        effective_timeout = timeout or self.config.timeout

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            raise OpenCLITimeoutError(
                f"opencli 命令超时 ({effective_timeout}s): {' '.join(args)}"
            )
        except FileNotFoundError:
            raise OpenCLINotFoundError(
                f"opencli 未找到，请确认已安装: npm install -g opencli"
            )

        if check_output and result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            stdout = result.stdout.strip() if result.stdout else ""

            # 认证错误检测
            auth_patterns = [
                "browser not connected",
                "not logged in",
                "login required",
                "authentication required",
                "session expired",
                "请先登录",
                "需要登录",
            ]
            combined_output = (stderr + " " + stdout).lower()
            for pattern in auth_patterns:
                if pattern.lower() in combined_output:
                    raise OpenCLIAuthError(
                        f"知乎登录态失效或浏览器未连接: {stderr or stdout}\n"
                        f"请先运行: opencli browser {self.config.browser_session} init"
                    )

            raise OpenCLIError(
                f"opencli 命令失败 (exit={result.returncode}): "
                f"{' '.join(args)}\n{stderr}"
            )

        return result

    def _run_json(
        self,
        args: List[str],
        timeout: Optional[int] = None,
    ) -> Any:
        """执行 opencli 命令并解析 JSON 输出

        Args:
            args: 命令行参数列表（不含 opencli 和 -f json）
            timeout: 超时时间

        Returns:
            解析后的 JSON 数据（可能是 dict、list 或 None）

        Raises:
            OpenCLIOutputError: JSON 解析失败
            OpenCLIAuthError: 认证问题
        """
        # 确保 JSON 格式
        full_args = list(args)
        if "-f" not in full_args and "--format" not in full_args:
            # 检查是否有 -f 或 --format 在 args 中
            if not any(arg in ("-f", "--format") for arg in full_args):
                full_args.extend(["-f", "json"])

        result = self._run(full_args, timeout=timeout)
        stdout = result.stdout.strip()

        if not stdout:
            return None

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            # 有时输出里会包含日志行，尝试找到 JSON 边界
            # 简单方法：尝试从第一个 { 或 [ 开始解析
            for start_char, end_char in [("{", "}"), ("[", "]")]:
                start = stdout.find(start_char)
                end = stdout.rfind(end_char)
                if start >= 0 and end > start:
                    try:
                        return json.loads(stdout[start:end + 1])
                    except json.JSONDecodeError:
                        continue

            raise OpenCLIOutputError(
                f"无法解析 opencli JSON 输出 (len={len(stdout)}): "
                f"{stdout[:200]}...\n解析错误: {e}"
            )

    # ========== Browser 子系统 ==========
    # 注意: opencli zhihu * 命令内部已封装浏览器操作，content/collection/hot/search
    # 都直接用 zhihu 命令。以下 browser 方法仅用于 zhihu 适配器未覆盖的场景
    #（如用户回答列表 DOM 提取）。

    def browser_open(self, url: str, session: Optional[str] = None) -> Dict:
        """在浏览器中打开 URL

        Args:
            url: 目标 URL
            session: 会话名称

        Returns:
            状态字典
        """
        sess = session or self.config.browser_session
        # browser 命令自带 JSON envelope，不加 -f json
        result = self._run(["browser", sess, "open", url])
        stdout = result.stdout.strip()
        if stdout:
            try:
                parsed = json.loads(stdout)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {"url": url}
        return {}

    def browser_eval(
        self,
        js: str,
        session: Optional[str] = None,
    ) -> Any:
        """在浏览器页面中执行 JavaScript

        Args:
            js: JavaScript 代码
            session: 会话名称

        Returns:
            JS 执行结果（自动解析 JSON）
        """
        sess = session or self.config.browser_session
        # browser 命令自带 JSON 输出，不加 -f json
        result = self._run(["browser", sess, "eval", js])
        stdout = result.stdout.strip()
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return stdout
        return None

    def browser_scroll(
        self,
        direction: str = "down",
        session: Optional[str] = None,
    ) -> None:
        """滚动浏览器页面

        Args:
            direction: 滚动方向 (up/down)
            session: 会话名称
        """
        sess = session or self.config.browser_session
        self._run(["browser", sess, "scroll", direction])

    def browser_wait(
        self,
        wait_type: str,
        value: str,
        session: Optional[str] = None,
    ) -> None:
        """等待页面条件

        Args:
            wait_type: 等待类型 (time/selector/text/xhr)
            value: 等待值
            session: 会话名称
        """
        sess = session or self.config.browser_session
        self._run(["browser", sess, "wait", wait_type, value])

    # ========== Zhihu 适配器方法 ==========

    def zhihu_answer_detail(
        self,
        answer_id: str,
        max_content: int = 0,
    ) -> Optional[Dict]:
        """获取知乎单个回答的完整内容

        对应: opencli zhihu answer-detail <id>

        Args:
            answer_id: 回答 ID（数字）、完整 URL 或 typed target
            max_content: 内容截断长度，0 表示不截断

        Returns:
            回答数据字典，字段: id, author, votes, comments, question_id,
            question_title, url, created_at, updated_at, content
        """
        args = ["zhihu", "answer-detail", str(answer_id)]
        if max_content:
            args.extend(["--max-content", str(max_content)])
        result = self._run_json(args, timeout=self.config.timeout)

        # 处理可能的 list 返回（opencli 某些版本/场景会返回数组）
        if isinstance(result, list):
            if len(result) == 0:
                return None
            result = result[0]  # 取第一个元素

        return result if isinstance(result, dict) else None

    def zhihu_collection(
        self,
        collection_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> List[Dict]:
        """获取知乎收藏夹内容列表（需要登录）

        对应: opencli zhihu collection <id>

        Args:
            collection_id: 收藏夹 ID
            offset: 起始偏移量
            limit: 每页数量（最大 20）

        Returns:
            条目列表，每项字段: rank, type, title, author, votes, excerpt, url
        """
        args = [
            "zhihu", "collection", str(collection_id),
            "--offset", str(offset),
            "--limit", str(limit),
        ]
        result = self._run_json(args)
        # collection 返回的是列表
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            # 可能包裹在某个 key 下
            for key in ("items", "data", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            # 单页直接返回 dict 的情况
            return [result] if result else []
        return []

    def zhihu_hot(self, limit: int = 20) -> List[Dict]:
        """获取知乎热榜

        对应: opencli zhihu hot

        Args:
            limit: 返回条目数

        Returns:
            热榜列表，每项字段: rank, title, heat, answers
        """
        args = ["zhihu", "hot", "--limit", str(limit)]
        result = self._run_json(args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("items", "data", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [result] if result else []
        return []

    def zhihu_search(
        self,
        query: str,
        search_type: str = "answer",
        limit: int = 20,
    ) -> List[Dict]:
        """知乎搜索

        对应: opencli zhihu search <query>

        Args:
            query: 搜索关键词
            search_type: 类型 (all/answer/article/question)
            limit: 返回数量

        Returns:
            搜索结果列表，每项字段: rank, title, type, author, votes, url
        """
        args = [
            "zhihu", "search", query,
            "--type", search_type,
            "--limit", str(limit),
        ]
        result = self._run_json(args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("items", "data", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [result] if result else []
        return []

    def zhihu_question(
        self,
        question_id: str,
        limit: int = 20,
    ) -> List[Dict]:
        """获取知乎问题详情和回答列表

        对应: opencli zhihu question <id>

        Args:
            question_id: 问题 ID
            limit: 返回回答数

        Returns:
            回答列表
        """
        args = [
            "zhihu", "question", str(question_id),
            "--limit", str(limit),
        ]
        result = self._run_json(args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("items", "data", "results", "answers"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [result] if result else []
        return []

    # ========== 便捷方法 ==========

    def get_user_answers_from_page(
        self,
        user_token: str,
        max_count: int = 100,
    ) -> List[Dict]:
        """通过 opencli zhihu user-answers 获取用户回答列表（带分页）

        直接调用 opencli zhihu user-answers 命令，支持分页获取大量回答。

        Args:
            user_token: 用户 url_token
            max_count: 最多获取数量

        Returns:
            回答摘要列表，每项: answer_id, question_id, question_title,
            question_url, created_time, content, vote_count, source_backend
        """
        try:
            all_answers = []
            offset = 0
            page_size = 20

            while len(all_answers) < max_count:
                page = self.zhihu_user_answers(
                    user_token,
                    limit=min(page_size, max_count - len(all_answers)),
                    offset=offset,
                )
                if not page:
                    break

                for a in page:
                    all_answers.append({
                        "answer_id": a.get("id", ""),
                        "question_id": a.get("questionId", ""),
                        "question_title": a.get("questionTitle", ""),
                        "question_url": a.get("url", ""),
                        "created_time": a.get("createdAt", ""),
                        "content": a.get("excerpt", ""),
                        "vote_count": a.get("votes", 0),
                        "source_backend": "opencli",
                    })

                if len(page) < page_size:
                    break  # no more pages
                offset += page_size
                time.sleep(self.config.request_delay)

            return all_answers
        except OpenCLIError:
            # Fallback: use browser eval if user-answers adapter is not installed
            return self._get_user_answers_via_browser(user_token)

    def _get_user_answers_via_browser(self, user_token: str) -> List[Dict]:
        """Fallback: 通过 browser eval 从用户回答页提取回答列表

        仅在 opencli zhihu user-answers 适配器未安装时使用。
        """
        answers_url = f"https://www.zhihu.com/people/{user_token}/answers"
        self.browser_open(answers_url)
        self.browser_wait("time", "3")

        js = r"""(function() {
            const results = [];
            document.querySelectorAll('.List-item, .ContentItem').forEach(function(item) {
                const link = item.querySelector('a[href*="/question/"][href*="/answer/"]');
                if (!link) return;
                const m = link.href.match(/\/question\/(\d+)\/answer\/(\d+)/);
                if (!m) return;
                const meta = item.querySelector('meta[itemprop="dateCreated"]');
                const time = item.querySelector('time[datetime]');
                results.push({
                    question_id: m[1],
                    answer_id: m[2],
                    question_title: link.innerText.trim().split('\n')[0],
                    created_time: (meta && meta.content) || (time && time.getAttribute('datetime')) || ''
                });
            });
            return results;
        })()"""

        result = self.browser_eval(js)
        if isinstance(result, list):
            return result
        return []

    def zhihu_user_answers(
        self,
        user_token: str,
        limit: int = 20,
        sort: str = "created",
        offset: int = 0,
    ) -> List[Dict]:
        """获取知乎用户回答列表

        对应: opencli zhihu user-answers <user_token>

        Args:
            user_token: 用户 url_token
            limit: 返回数量（最大1000）
            sort: 排序方式 (created/default)
            offset: 起始偏移

        Returns:
            回答列表，每项字段: rank, id, author, questionId, questionTitle,
            votes, createdAt, url, excerpt
        """
        args = [
            "zhihu", "user-answers", user_token,
            "--limit", str(limit),
            "--sort", sort,
            "--offset", str(offset),
        ]
        result = self._run_json(args)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("items", "data", "results"):
                if key in result and isinstance(result[key], list):
                    return result[key]
            return [result] if result else []
        return []

    @staticmethod
    def convert_answer_detail_to_legacy(detail: Any) -> Optional[Dict]:
        """将 OpenCLI answer-detail 输出转换为现有爬虫的 JSON 格式

        OpenCLI 字段: id, author, votes, comments, question_id, question_title,
                      url, created_at, updated_at, content
        现有格式字段: answer_id, question_id, question_title, question_url,
                      content, vote_count, created_time

        Args:
            detail: opencli answer-detail 返回的 dict 或 list

        Returns:
            与现有 Playwright 爬虫格式兼容的 dict，解析失败返回 None
        """
        # 处理可能的 list 返回
        if isinstance(detail, list):
            if len(detail) == 0:
                return None
            detail = detail[0]

        if not isinstance(detail, dict):
            return None

        return {
            "answer_id": str(detail.get("id", "")),
            "question_id": str(detail.get("question_id", "")),
            "question_title": detail.get("question_title", ""),
            "question_url": detail.get("url", ""),
            "content": detail.get("content", ""),
            "vote_count": detail.get("votes", 0),
            "created_time": detail.get("created_at", ""),
            "author": detail.get("author", ""),
            "comments_count": detail.get("comments", 0),
            "source_backend": "opencli",
        }


# ========== 工厂函数 ==========

def create_runner_from_config() -> OpenCLIRunner:
    """从项目配置文件创建 OpenCLIRunner 实例"""
    from core.config import OPENCLI_CONFIG

    opencli_config = OpenCLIConfig(
        binary_path=OPENCLI_CONFIG.get("binary_path", "opencli"),
        browser_session=OPENCLI_CONFIG.get("browser_session", "zhihu"),
        window_mode=OPENCLI_CONFIG.get("window_mode", "background"),
        site_session=OPENCLI_CONFIG.get("site_session", "persistent"),
        timeout=OPENCLI_CONFIG.get("timeout", 120),
        request_delay=OPENCLI_CONFIG.get("request_delay", 2.0),
        output_format=OPENCLI_CONFIG.get("format", "json"),
    )
    return OpenCLIRunner(opencli_config)
