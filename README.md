# 知乎爬虫工具 (Python 重构版)

使用 Python 重构的知乎数据爬取工具，基于 Playwright 实现浏览器自动化。

## 项目特点

- **Python 重构**: 使用 Python 3.8+ 和 asyncio 实现异步爬取
- **模块化设计**: 清晰的模块划分，易于维护和扩展
- **断点续爬**: 支持检查点机制，中断后可从上次位置继续
- **数据分批保存**: 自动分批保存数据，避免内存溢出
- **类型注解**: 完整的类型注解，提高代码可读性

## 项目结构

```
zhihu_crawler/
├── core/                       # 核心模块
│   ├── __init__.py
│   ├── config.py              # 配置文件
│   └── zhihu_api.py           # 知乎 API 封装
├── utils/                      # 工具模块
│   ├── __init__.py
│   ├── checkpoint.py          # 检查点管理
│   └── storage.py             # 数据存储
├── scripts/                    # 脚本目录
│   ├── crawl_aote.py          # 爬取奥特之父
│   └── save_auth.py           # 保存登录凭证
├── output/                     # 输出目录
├── data/                       # 数据目录
├── requirements.txt            # 依赖列表
└── README.md                   # 项目说明
```

## 安装依赖

```bash
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

## 使用方法

### 1. 保存登录凭证

首次使用需要先登录知乎并保存凭证：

```bash
cd zhihu_crawler
python scripts/save_auth.py
```

脚本会打开浏览器，请手动登录知乎，登录成功后脚本会自动保存凭证。

### 2. 爬取数据

保存凭证后，运行爬取脚本：

```bash
python scripts/crawl_aote.py
```

脚本会自动爬取奥特之父的所有知乎回答，并保存到 `output/` 目录。

### 3. 断点续爬

如果爬取过程中断，再次运行脚本会自动从上次的位置继续爬取。

## 配置文件

编辑 `core/config.py` 可以修改配置：

```python
# 爬虫配置
CRAWLER_CONFIG = {
    "batch_size": 50,           # 每批保存的数据量
    "request_delay": 2.0,     # 请求间隔（秒）
    "max_retries": 5,          # 最大重试次数
    "headless": True,          # 是否无头模式
}

# 目标用户
TARGET_USERS = {
    "奥特之父": {
        "url_token": "xu-ze-qiu",
        "expected_answers": 4832,
    },
}
```

## 数据输出格式

爬取的数据以 JSON 格式保存，每条回答包含以下字段：

```json
{
  "id": "123456789",
  "type": "answer",
  "question": {
    "id": "987654321",
    "title": "问题标题"
  },
  "content": "<p>回答内容（HTML格式）</p>",
  "voteup_count": 100,
  "comment_count": 50,
  "created_time": 1234567890,
  "url": "https://www.zhihu.com/question/.../answer/..."
}
```

## 注意事项

1. **频率限制**: 知乎有反爬机制，请合理设置请求间隔（默认2秒）
2. **登录状态**: 登录凭证会过期，如遇到403错误请重新运行 `save_auth.py`
3. **数据量**: 大量数据爬取可能需要较长时间，请保持网络稳定
4. **合法性**: 请遵守知乎用户协议和相关法律法规

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 PR！
