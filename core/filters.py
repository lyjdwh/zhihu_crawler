"""
共享过滤和解析模块 - Playwright 和 OpenCLI 爬虫共用

提供主题关键词匹配、日期解析等功能，避免在两个后端之间重复代码。
"""

import re
from datetime import datetime, timedelta
from typing import Optional

# ============ 主题关键词 ============

TOPIC_KEYWORDS = {
    "finance": [
        "A股", "股市", "股票", "大盘", "涨停", "跌停", "牛市", "熊市",
        "抄底", "基金", "投资", "理财", "金融", "沪指", "创业板",
        "光伏", "宁德", "比亚迪", "小米", "英伟达", "格力", "蔚来",
        "智界", "油价", "石油", "黄金", "美元", "人民币", "汇率",
        "国债", "债市", "期货", "期权", "量化", "私募", "公募",
        "IPO", "转债", "融券", "融资", "配股", "分红", "股息",
        "茅台", "特斯拉", "恒生", "纳斯达克", "标普", "道琼斯",
        "上证", "深证", "科创", "北交所", "ETF", "LOF",
    ],
    "tech": [
        "AI", "人工智能", "大模型", "ChatGPT", "GPT", "Claude",
        "芯片", "半导体", "CPU", "GPU", "英伟达", "AMD", "英特尔",
        "手机", "华为", "苹果", "小米", "OPPO", "vivo", "三星",
        "新能源", "电动车", "特斯拉", "比亚迪", "自动驾驶", "智驾",
        "机器人", "具身智能", "人形机器人", "宇树",
    ],
    "international": [
        "伊朗", "以色列", "中东", "霍尔木兹", "美军", "战争",
        "哈梅内伊", "美国", "特朗普", "拜登", "普京", "俄罗斯",
        "乌克兰", "日本", "韩国", "朝鲜", "台海", "南海", "中美",
        "G7", "北约", "欧盟", "关税", "制裁",
    ],
    "culture": [
        "动漫", "漫画", "龙珠", "JoJo", "鸟山明", "镖人",
        "电影", "票房", "春节档", "热辣滚烫", "飞驰人生",
        "音乐", "游戏", "主播", "直播", "短视频",
    ],
    "life": [
        "买房", "房价", "房子", "别墅", "装修", "房贷",
        "工作", "职场", "创业", "裁员", "就业", "工资",
        "恋爱", "婚姻", "相亲", "出轨", "老婆", "老公",
    ],
}


def check_topic(text: str, topic: str) -> bool:
    """检查文本是否匹配指定主题

    Args:
        text: 要检查的文本（通常是问题标题）
        topic: 主题标识 (all/finance/tech/international/culture/life 或自定义关键词)

    Returns:
        True 如果文本匹配主题
    """
    if topic == "all":
        return True

    keywords = TOPIC_KEYWORDS.get(topic, [])
    if not keywords:
        # 如果不是预定义主题，直接用关键词匹配
        return topic.lower() in text.lower()

    return any(kw in text for kw in keywords)


def get_keywords_for_topic(topic: str) -> list:
    """获取指定主题的关键词列表

    Args:
        topic: 主题标识

    Returns:
        关键词列表，未找到时返回空列表
    """
    return TOPIC_KEYWORDS.get(topic, [])


def parse_zhihu_date(date_str: str) -> Optional[datetime]:
    """解析多种格式的知乎日期字符串

    支持格式:
    - ISO 8601: 2026-03-15T10:30:00.000Z, 2026-03-15T10:30:00
    - 简单日期: 2026-03-15, 2026年3月15日
    - 相对时间: "x 小时前", "x 天前", "昨天", "前天"
    - 嵌入日期: "发布于 2026-03-15"

    Args:
        date_str: 日期字符串

    Returns:
        datetime 对象，解析失败返回 None
    """
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
    now = datetime.now().astimezone()

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


def filter_by_date(
    date_str: str,
    after_dt: Optional[datetime] = None,
    before_dt: Optional[datetime] = None,
) -> bool:
    """检查日期是否在指定范围内

    Args:
        date_str: 日期字符串（任意知乎支持的格式）
        after_dt: 开始日期（包含），None 表示不限制
        before_dt: 结束日期（包含），None 表示不限制

    Returns:
        True 如果日期在范围内或无需过滤
    """
    if not after_dt and not before_dt:
        return True

    if not date_str:
        # 没有日期信息时，保守处理（不过滤）
        return True

    answer_dt = parse_zhihu_date(date_str)
    if answer_dt is None:
        # 无法解析日期，保守处理
        return True

    if after_dt and answer_dt < after_dt:
        return False
    if before_dt and answer_dt > before_dt:
        return False

    return True
