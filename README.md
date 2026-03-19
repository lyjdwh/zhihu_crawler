# 知乎爬虫工具

基于 Playwright 的知乎数据爬取工具，支持爬取用户回答、收藏夹内容，用于构建每日股市推荐系统。

## 项目特点

- **异步爬取**: 使用 Python asyncio 实现高效爬取
- **模块化设计**: 清晰的模块划分，易于维护和扩展
- **断点续爬**: 支持检查点机制，中断后可从上次位置继续
- **日期筛选**: 支持按日期范围筛选回答
- **主题过滤**: 支持按关键词过滤特定主题的回答
- **多种数据源**: 支持爬取用户回答和收藏夹内容
- **完整内容获取**: 自动展开完整回答内容
- **图片爬取**: 自动提取并下载回答中的图片，图片位置标记插入原文对应位置

## 项目结构

```
zhihu_crawler/
├── core/                       # 核心模块
│   ├── __init__.py
│   ├── config.py              # 配置文件（目标用户、爬虫配置）
│   ├── browser.py             # 浏览器管理（反爬措施、Playwright 封装）
│   └── zhihu_api.py           # 知乎 API 封装
├── utils/                      # 工具模块
│   ├── __init__.py
│   ├── checkpoint.py          # 检查点管理
│   ├── storage.py             # 数据存储
│   └── image_downloader.py    # 图片异步下载工具
├── scripts/                    # 爬虫脚本
│   ├── crawl_user.py          # 用户回答爬虫（支持日期/主题过滤）
│   ├── crawl_collection.py    # 收藏夹爬虫（支持分页）
│   └── save_auth.py           # 保存登录凭证
├── output/                     # 输出目录
│   └── images/                # 图片存储目录
├── data/                       # 数据目录（登录凭证）
├── docs/                       # 文档
├── requirements.txt            # 依赖列表
└── setup.py                    # 安装配置
```

## 安装

```bash
# 克隆项目
git clone https://github.com/lyjdwh/zhihu_crawler.git
cd zhihu_crawler

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

## 快速开始

### 1. 保存登录凭证

首次使用需要先登录知乎并保存凭证：

```bash
python scripts/save_auth.py
```

脚本会打开浏览器，请手动登录知乎，登录成功后脚本会自动保存凭证。

### 2. 爬取用户回答

```bash
# 爬取指定用户金融相关回答
python scripts/crawl_user.py --user xu-ze-qiu --topic finance --count 100

# 按日期筛选
python scripts/crawl_user.py --user xu-ze-qiu --after-date 2026-03-01 --topic finance

# 组合使用
python scripts/crawl_user.py --user xu-ze-qiu --count 50 --topic finance --after-date 2026-01-01

# 爬取 MR Dang
python scripts/crawl_user.py --user mr-dang-77 --topic finance --count 100
```

### 3. 爬取收藏夹

```bash
python scripts/crawl_collection.py --collection 860134416 --count 200
```

## 命令行参数

### crawl_user.py

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--user` | 用户 url_token | 必填 |
| `--topic` | 主题过滤关键词 | finance |
| `--count` | 目标数量 | 100 |
| `--after-date` | 筛选日期之后 | 无 |
| `--before-date` | 筛选日期之前 | 无 |
| `--headless` | 无头模式 | true |
| `--no-extract-images` | 关闭图片提取 | 默认开启 |
| `--no-download-images` | 只提取图片URL不下载 | 默认下载 |
| `--image-quality` | 图片质量（raw/hd/normal/thumbnail） | hd |
| `--image-path` | 自定义图片存储路径 | output/images |

### crawl_collection.py

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--collection` | 收藏夹 ID | 必填 |
| `--count` | 目标数量 | 100 |
| `--type` | 内容类型（answer/article） | 全部 |
| `--headless` | 无头模式 | true |
| `--no-extract-images` | 关闭图片提取 | 默认开启 |
| `--no-download-images` | 只提取图片URL不下载 | 默认下载 |
| `--image-quality` | 图片质量（raw/hd/normal/thumbnail） | hd |
| `--image-path` | 自定义图片存储路径 | output/images |

### 主题过滤选项

- `finance` - 金融/投资/股市
- `tech` - 科技/AI/手机
- `international` - 国际形势
- `culture` - 动漫/电影/游戏
- `life` - 生活/职场/情感

## 配置文件

编辑 `core/config.py` 可以修改配置：

```python
# 目标用户
TARGET_USERS = {
    "xu-ze-qiu": {
        "url_token": "xu-ze-qiu",
        "expected_answers": 4832,
    },
    "mr-dang-77": {
        "url_token": "mr-dang-77",
        "expected_answers": 142,
    }
}

# 爬虫配置
CRAWLER_CONFIG = {
    "batch_size": 50,
    "request_delay": 2.0,
    "max_retries": 5,
    "headless": True,
}
```

## 数据输出格式

爬取的数据以 JSON 格式保存在 `output/` 目录：

```json
{
  "answer_id": "123456789",
  "question_id": "987654321",
  "question_title": "问题标题",
  "question_url": "https://www.zhihu.com/question/...",
  "content": "回答内容（图片位置插入[图片：路径]标记）",
  "content_html": "HTML格式内容",
  "images": [
    {
      "url": "图片原始URL",
      "alt": "图片alt属性",
      "local_path": "本地存储绝对路径",
      "relative_path": "本地存储相对路径",
      "width": 800,
      "height": 600,
      "position": 42,
      "download_success": true
    }
  ],
  "vote_count": 100,
  "created_time": "2026-03-15"
}
```

图片存储路径规则：
- 用户回答：`output/images/{user_id}/{answer_id}_{index}.{ext}`
- 收藏夹：`output/images/collection_{collection_id}/{answer_id}_{index}.{ext}`

## 每日股市推荐系统

本项目可用于构建每日股市推荐系统：

1. 爬取知乎专家（如 xu-ze-qiu、mr-dang-77）的金融回答
2. 分析提取股票/ETF 推荐信息
3. 生成每日股市推荐报告

详细说明见 [docs/每日荐股系统需求.md](./docs/每日荐股系统需求.md)

## 注意事项

1. **频率限制**: 知乎有反爬机制，请合理设置请求间隔
2. **登录状态**: 登录凭证会过期，如遇到 403 错误请重新运行 `save_auth.py`
3. **数据量**: 大量数据爬取可能需要较长时间，请保持网络稳定
4. **合法性**: 请遵守知乎用户协议和相关法律法规

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 PR！