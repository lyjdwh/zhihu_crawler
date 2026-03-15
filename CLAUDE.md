# CLAUDE.md - 知乎爬虫项目指南

## 项目概述

基于 Playwright 的知乎数据爬取工具，支持爬取用户回答、收藏夹内容，用于构建每日股市推荐系统。

## 项目结构

```
zhihu_crawler/
├── scripts/              # 爬虫脚本
│   ├── crawl_user.py    # 用户回答爬虫（支持日期/主题过滤）
│   └── crawl_collection.py  # 收藏夹爬虫（支持分页）
├── output/               # 输出数据
│   ├── xu-ze-qiu_finance.json   # 奥特之父金融回答
│   ├── mr_dang_finance.json     # MR Dang金融回答
│   ├── my_collection.json       # 个人收藏夹
│   └── 每日股市推荐报告_*.md    # 每日推荐报告
├── data/                 # 数据文件
│   └── zhihu_auth.json  # 知乎登录态（需自行配置）
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

## 注意事项

- 需要在 `data/zhihu_auth.json` 中配置登录态
- 爬取过程中会有延迟，避免过快请求
- 收藏夹最多爬取10页（约112条），知乎限制
- 生成报告需要运行爬虫获取最新数据

## 扩展

- 可增加更多知乎专家
- 可接入股票行情API
- 可实现微信/邮件推送