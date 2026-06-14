# CLAUDE.md - 知乎爬虫项目指南

## 项目概述

基于 Playwright 和 OpenCLI 双后端的知乎数据爬取工具，支持爬取用户回答、收藏夹内容、热榜，用于构建每日股市推荐系统。

## 项目结构

```
zhihu_crawler/
├── scripts/              # 爬虫脚本
│   ├── crawl_user.py    # 用户回答爬虫（Playwright 后端）
│   ├── crawl_collection.py  # 收藏夹爬虫（Playwright 后端）
│   ├── crawl_user_opencli.py    # 用户回答爬虫（OpenCLI 后端）
│   ├── crawl_collection_opencli.py  # 收藏夹爬虫（OpenCLI 后端）
│   └── crawl_hot_opencli.py   # 热榜爬虫（OpenCLI 独有新能力）
├── core/                 # 核心模块
│   ├── browser.py       # Playwright 浏览器管理
│   ├── opencli_runner.py # OpenCLI 子进程封装
│   ├── filters.py       # 共享过滤模块（主题/日期）
│   └── config.py        # 全局配置（含 OpenCLI 配置）
├── utils/                # 工具模块
│   ├── image_downloader.py  # 图片异步下载工具
│   └── checkpoint.py    # 断点续爬
├── output/               # 输出数据
│   ├── xu-ze-qiu_finance.json   # 奥特之父金融回答
│   ├── mr_dang_finance.json     # MR Dang金融回答
│   ├── my_collection.json       # 个人收藏夹
│   ├── 每日股市推荐报告_*.md    # 每日推荐报告
│   └── images/          # 下载的图片（按用户ID分目录）
├── data/                 # 数据文件
│   └── zhihu_auth.json  # 知乎登录态（Playwright 用，OpenCLI 不需要）
└── docs/                 # 文档
    └── 每日荐股系统需求.md
```

## 常用命令

### 爬取用户回答
```bash
# 爬取指定用户金融相关回答
python scripts/crawl_user.py --user xu-ze-qiu --topic finance --count 100

# 按日期筛选
python scripts/crawl_user.py --user xu-ze-qiu --after-date 2026-03-01 --topic finance

# 组合使用
python scripts/crawl_user.py --user xu-ze-qiu --count 50 --topic finance --after-date 2026-01-01
```

### 爬取收藏夹
```bash
python scripts/crawl_collection.py --collection 860134416 --count 200
```

### 主题过滤选项
- `finance` - 金融/投资/股市
- `tech` - 科技/AI/手机
- `international` - 国际形势
- `culture` - 动漫/电影/游戏
- `life` - 生活/职场/情感
- 自定义关键词

## OpenCLI 使用方法 (替代后端)

### 前置条件
```bash
# 1. 安装 opencli
npm install -g opencli

# 2. 安装 Chrome 扩展（首次使用 opencli 会自动提示）
#    在 Chrome 中打开知乎并登录

# 3. 验证（无需手动 bind，zhihu 命令内部自动管理浏览器）
opencli zhihu hot --limit 5 -f json
```

### 爬取用户回答 (OpenCLI 版)
```bash
# 参数完全对齐 Playwright 版
python scripts/crawl_user_opencli.py --user xu-ze-qiu --count 50 --topic finance
python scripts/crawl_user_opencli.py --user xu-ze-qiu --after-date 2026-03-01 --topic finance
python scripts/crawl_user_opencli.py --user xu-ze-qiu --count 50 --no-content --no-extract-images
```

### 爬取收藏夹 (OpenCLI 版)
```bash
python scripts/crawl_collection_opencli.py --collection 860134416 --count 200
```

### 爬取热榜 (OpenCLI 独有新能力)
```bash
python scripts/crawl_hot_opencli.py --limit 20
python scripts/crawl_hot_opencli.py --limit 30 --output output/hot_today.json
```

### OpenCLI vs Playwright 对比

| 维度 | Playwright | OpenCLI |
|------|-----------|---------|
| 安装 | `pip install playwright` | `npm install -g opencli` |
| 登录方式 | auth.json storage state | 真人浏览器窗口登录 |
| 反爬能力 | 中等（需手动配置反爬参数） | 强（真人浏览器指纹） |
| 维护成本 | 需维护选择器、反爬逻辑 | 低（adapter 持续更新） |
| 输出格式 | 自定义 JSON | JSON/YAML/Table/CSV/MD |
| 热榜支持 | 无 | 有 (`zhihu hot`) |
| 图片提取 | 完整支持（HTML 解析） | 有限（需额外 browser eval） |
| 离线使用 | 是 | 否（通过浏览器桥接） |

## 技术要点

### 0. 调试技巧
- 调试时使用 `headless=False` 观察页面行为
- 先用单条内容测试再批量爬取

### 1. 分页处理
收藏夹爬虫使用点击"下一页"按钮实现分页，选择器：
```python
'.Pagination-next, .Paginator-next, button:has-text("下一页"), a:has-text("下一页")'
```

### 2. 获取完整内容
知乎回答默认只显示摘要（约100字符），需要：
1. 滚动到页面底部触发懒加载: `window.scrollTo(0, document.body.scrollHeight)`
2. 内容选择器优先使用 `.AnswerItem` 或 `.zm-item-answer` 容器
3. 阈值设为500字符判断列表页内容是否足够（列表页通常<200字符）

### 3. 反爬措施
- 使用 `--disable-blink-features=AutomationControlled` 参数
- 设置 `navigator.webdriver` 为 undefined
- 使用真实 User-Agent
- 添加适当延迟

### 4. 图片数据字段
- `images[].local_path`: 完整绝对路径，直接用 Read 工具读取
- `images[].relative_path`: 相对路径（相对于 output/images/）
- 图片存储：`output/images/{user_id}/{answer_id}_{index}.{ext}`

## 注意事项

- 需要在 `data/zhihu_auth.json` 中配置登录态
- 爬取过程中会有延迟，避免过快请求
- 收藏夹最多爬取10页（约112条），知乎限制
- 生成报告需要运行爬虫获取最新数据

## 扩展

- 可增加更多知乎专家
- 可接入股票行情API
- 可实现微信/邮件推送

## 【重要】生成股市推荐报告要求

**生成报告前务必阅读 `docs/每日荐股系统需求.md`**

### 报告格式要求（来自需求文档）：

1. **结论放前面**：今日操作建议、推荐股票/ETF、风险提示放在报告最前面
2. **分析放后面**：专家观点、收藏夹理念等详细分析放在后面
3. **具体股票信息**：包含代码、名称、推荐理由、目标价、止损价、操作建议
4. **风险提示**：标注具体风险和仓位建议
5. **数据来源**：统计各专家的回答数量

### 报告输出格式参考：

```markdown
# 每日股市推荐报告 (YYYY-MM-DD)

## 【结论】今日操作建议
[核心操作建议放最前面]

### 重点推荐股票/ETF
| 类型 | 名称 | 代码 | 操作 | 风险 |
|------|------|------|------|------|

### 风险提示
[具体风险点]

## 【图表】 周末市场回顾与周一展望
[分析内容...]
```

### 生成报告流程：

1. 爬取专家最新回答：
   ```bash
   python scripts/crawl_user.py --user xu-ze-qiu --after-date $(date -d '7 days ago' +%Y-%m-%d)
   python scripts/crawl_user.py --user mr-dang-77 --after-date $(date -d '7 days ago' +%Y-%m-%d)
   ```
2. 分析提取股票信息
3. 参考需求文档格式生成报告
4. 结论前置，分析后置