# 每日信息抓取 (Daily Info Scraper)

一个**可插拔**的信息抓取框架：从多个结构化平台（arXiv 论文、Hacker News 等）抓取最新内容，按数据源分类归档为 Markdown，可选推送到个人微信（PushPlus / Server酱）。

> 设计思路与 [news-daily](https://github.com/kabbmam-netizen/news-daily) 一脉相承：纯 RSS/API 抓取，无 AI、无数据库、无付费 API；源做成模块，加源只需新建一个文件 + 配置一条。

## 当前数据源

| 模块 | 来源 | 抓什么 |
|------|------|--------|
| `arxiv` | arXiv 官方 API | 指定分类的最新论文（如 cs.AI/cs.CL/cs.LG） |
| `hackernews` | HN 官方 RSS | 首页热帖 + Show HN 项目 |

加新源：在 `src/sources/` 下新建一个继承 `BaseSource` 的模块，自动注册，无需改其他代码。

- **调度**：GitHub Actions 每天 UTC 22:00（北京时间次日 06:00）自动运行
- **输出**：`digests/YYYY-MM-DD.md`，提交回仓库
- **推送**：通过 webhook 推送到个人微信 / 企业微信 / 钉钉（按 URL 域名自动识别）

## 本地运行

```bash
pip install -r requirements.txt
python -m src.main
```

生成的摘要存放在 `digests/` 目录。设置 `WEBHOOK_URL` 环境变量后会同时推送：

```bash
# Windows PowerShell
$env:WEBHOOK_URL="https://www.pushplus.plus/send?token=xxx"
python -m src.main

# Linux / macOS
export WEBHOOK_URL="https://www.pushplus.plus/send?token=xxx"
python -m src.main
```

## 配置数据源

编辑 `config.yml`。每个源一个配置块，`enabled: false` 可临时关闭某源：

```yaml
sources:
  arxiv:
    enabled: true
    categories: [cs.AI, cs.CL, cs.LG]
    max_results: 15      # 每个分类抓多少篇
```

全局设置：

- `max_items_per_source`：每个**分类**保留多少条（newest first）
- `max_push_items`：微信推送最多多少条（防超长）
- `timezone_offset`：时区偏移（默认 8 = 北京时间），用于标注摘要日期

## 加一个新数据源

1. 在 `src/sources/` 下新建 `mysource.py`：

   ```python
   from .base import BaseSource
   from ..items import InfoItem

   class MySource(BaseSource):
       name = "mysource"            # 必须与 config.yml 的 block 名一致
       display_name = "我的来源"
       emoji = "🔖"

       def fetch(self, config: dict):
           # 抓取逻辑，失败返回 []，不要抛异常
           return [InfoItem(...)]
   ```

2. 在 `config.yml` 加配置块：

   ```yaml
   sources:
     mysource:
       enabled: true
       # ...你的配置
   ```

3. 完成。下次运行自动发现并抓取该源。

## 部署到 GitHub Actions

1. 把项目推到 GitHub 仓库
2. （可选）配 webhook secret：仓库 **Settings -> Secrets and variables -> Actions -> New repository secret**，Name 填 `WEBHOOK_URL`，Value 填 PushPlus / Server酱 / 企业微信 / 钉钉地址
3. 手动触发验证：**Actions** -> `Daily Info Scrape` -> `Run workflow`
4. 之后每天北京时间早上 6 点自动运行

## 获取 Webhook 地址

### PushPlus（推送到个人微信，推荐）
微信扫码登录 https://www.pushplus.plus/ 并关注公众号 + **完成实名认证**（未实名无法发送），拿到 token，拼成 `https://www.pushplus.plus/send?token={token}` 作为 `WEBHOOK_URL`。

### Server酱（推送到个人微信）
微信扫码登录 https://sct.ftqq.com/ 拿到 SendKey，拼成 `https://sctapi.ftqq.com/{sendkey}.send`。

### 企业微信群 / 钉钉
见 `.env.example` 顶部说明。

## 项目结构

```
info-scraper/
├── .github/workflows/daily-scrape.yml   # GitHub Actions 定时任务
├── digests/                             # 生成的每日摘要（自动提交）
├── src/
│   ├── main.py                          # 入口：发现源 -> 抓取 -> 归档 -> 推送
│   ├── config.py                        # 读取 config.yml
│   ├── items.py                         # InfoItem 数据类
│   ├── notifiers.py                     # PushPlus/Server酱/企业微信/钉钉 推送
│   └── sources/
│       ├── __init__.py                  # 源注册表（自动发现）
│       ├── base.py                      # BaseSource 抽象基类
│       ├── arxiv.py                     # arXiv 论文
│       └── hackernews.py               # Hacker News
├── config.yml                           # 数据源配置（可自由增删）
├── requirements.txt
└── README.md
```

## 工作原理

1. `config.yml` 定义各数据源配置
2. `src/sources/__init__.py` 自动发现 `src/sources/` 下所有 `BaseSource` 子类
3. 每个 enabled 的源调用 `fetch()`，失败返回 `[]` 不影响其他源
4. 按**分类**截断、按 URL 跨源去重、按时间倒序
5. `main.py` 生成 Markdown 归档 + 微信推送（前 N 条速览）
6. GitHub Actions 把摘要提交回仓库

## License

MIT - 可自由使用、修改、分发。
