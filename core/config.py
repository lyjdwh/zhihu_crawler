"""
知乎爬虫配置文件
"""
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 输出目录
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 数据目录
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# 知乎配置
ZHIHU_CONFIG = {
    "base_url": "https://www.zhihu.com",
    "api_url": "https://www.zhihu.com/api/v4",
    "auth_file": DATA_DIR / "zhihu_auth.json",
    "checkpoint_file": DATA_DIR / "checkpoint.json",
}

# 爬虫配置
CRAWLER_CONFIG = {
    "batch_size": 50,
    "request_delay": 2.0,  # 请求间隔（秒）
    "max_retries": 5,
    "headless": True,
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}

# 目标用户配置
TARGET_USERS = {
    "奥特之父": {
        "url_token": "xu-ze-qiu",
        "expected_answers": 4832,
    },
    "MR_DANG": {
        "url_token": "mr-dang-77",
        "expected_answers": 142,
    }
}
