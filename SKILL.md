---
name: quick-web-search
description: >
  Search the web through a self-hosted SearXNG instance with a lightweight but
  quality-aware pipeline. Also includes an RSS/Atom Feed sub-command (rss_fetch.py)
  for subscribing, fetching, and monitoring blog/news feeds — zero API fees.
  Use when you need a quick web lookup, current information, recent news, or broad
  internet context. Also use when tracking blog updates, ArXiv papers, or GitHub
  Releases via RSS feeds.
---

# Quick Web Search

Use this skill as the **quick-search + feed reader** companion to `deep-search-research`.

It keeps the retrieval path lightweight, covering two complementary modes:
- **Search** (reactive) — use `searxng_search.py` to look up anything on the web
- **RSS Feed** (proactive) — use `rss_fetch.py` to subscribe to and monitor blog/news feeds

## Search workflow

1. Use `scripts/searxng_search.py` for quick web lookups.
2. Keep the task lightweight: find, scan, shortlist, or gather current context.
3. If the user needs a report, research plan, claim tracing, or multi-platform synthesis, switch to `deep-search-research`.

### Search command patterns

Basic search:
```bash
py scripts/searxng_search.py "your query"
```

Tech or news search:
```bash
py scripts/searxng_search.py "latest browser automation agent news" --categories news --time-range day --max-results 5
py scripts/searxng_search.py "open source coding assistant" --categories it --max-results 8
```

Human-readable output:
```bash
py scripts/searxng_search.py "OpenClaw" --text
```

Health check:
```bash
py scripts/searxng_search.py --health
```

### Search output contract

The script returns JSON with:
- `query`, `results`, `suggestions`, `answers`, `total_results`, `error`, `meta`

Each result includes: title, url, snippet, engines, score, category, source_type, query_variant, quality.

---

## RSS Feed workflow

Use `scripts/rss_fetch.py` for feed-based information retrieval.
Complements search: search finds what you ask for; feeds push what you subscribe to.

### Prerequisites

```bash
pip install feedparser
```

### RSS commands

**Fetch** latest entries from a Feed URL:
```bash
py scripts/rss_fetch.py fetch "https://hnrss.org/newest" --limit 10
py scripts/rss_fetch.py fetch "https://www.ruanyifeng.com/blog/atom.xml" --limit 3
py scripts/rss_fetch.py fetch "https://hnrss.org/newest" --since "2026-04-01"
```

**Subscribe** to feeds:
```bash
py scripts/rss_fetch.py add "阮一峰" --url "https://www.ruanyifeng.com/blog/atom.xml"
py scripts/rss_fetch.py add "Hacker News" --url "https://hnrss.org/newest"
```

**List** subscriptions:
```bash
py scripts/rss_fetch.py list
```

**Monitor** for new entries (incremental — only outputs entries since last check):
```bash
py scripts/rss_fetch.py monitor
```

**Health check** a feed:
```bash
py scripts/rss_fetch.py health "https://hnrss.org/newest"
```

### RSS command patterns

| Action | Example |
|--------|---------|
| **fetch** | `fetch <url> [--limit N] [--since "YYYY-MM-DD"]` |
| **add** | `add [name] --url <feed-url>` |
| **remove** | `remove <url-or-name>` |
| **list** | `list [--feeds-file PATH]` |
| **monitor** | `monitor [--feeds-file PATH] [--url URL] [--limit N]` |
| **health** | `health <url>` |

### Common Feed sources

| Source | URL |
|--------|-----|
| Hacker News | `https://hnrss.org/newest` |
| 阮一峰网络日志 | `https://www.ruanyifeng.com/blog/atom.xml` |
| 36Kr | `https://36kr.com/feed` |
| ArXiv CS.AI | `https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&max_results=10` |
| GitHub Releases | `https://github.com/<owner>/<repo>/releases.atom` |

### Cron integration

Pair with `cron-manager` for scheduled feed monitoring:
```
定时任务：使用 rss_fetch.py monitor 检查所有已订阅源的新文章，
如果有新文章，以简洁格式列出标题和链接。
如果没有新文章，不输出任何内容。
```

---

## Guardrails

- Treat search as **fast search**, not deep research.
- Prefer the original query plus one focused variant; do not turn quick search into a large retrieval job.
- Preserve error transparency. If SearXNG is unreachable or rate-limited, surface it clearly.
- RSS is best for structured, syndicated content (blogs, news, ArXiv, releases).
- For platform-specific data (B站/小红书/Twitter), use `opencli-bridge`.
- For scraping arbitrary web pages, use `scrapling-plus`.

## Notes

- Auto-start is supported for the local SearXNG deployment.
- The quick-search path intentionally stays cheaper and shallower than `deep-search-research`.
- RSS subscriptions are stored at `~/.openclaw/rss-subscribe/feeds.json` (independent of workspace).
- RSS requires `feedparser` Python package (`pip install feedparser`).

---

## 搜索规范（建议采用）

以下规范用于提升搜索结果的可信度和可追溯性，作为**建议性内容**，可根据任务复杂度选择采用。

### 证据链规范

#### 来源分级

| 级别 | 类型 | 示例 | 可信度 |
|------|------|------|--------|
| 1 | 官方/原始 | 官方公告、法规原文、论文原文、招股书 | 最高 |
| 2 | 权威机构 | 研究机构、专业出版社、监管机构 | 高 |
| 3 | 主流媒体 | 高质量新闻媒体、专业数据库 | 中高 |
| 4 | 二手来源 | 转引、摘要、博客 | 中 |
| 5 | 社交/论坛 | Twitter、Reddit、论坛帖子 | 低（仅作线索） |

#### 证据链要求

| 风险等级 | 来源要求 |
|----------|----------|
| 低风险（普通事实） | ≥1 个高可信来源 |
| 中风险（重要结论） | ≥2 个独立来源，其中 1 个为官方/原始 |
| 高风险（决策依据） | ≥2-3 个来源，必须含原始来源 |

#### 社交平台使用规则

- ✅ 可作为线索发现来源
- ❌ 不能单独作为结论依据
- ⚠️ 必须回查到官网、媒体或原始文件

### 来源优先级

按以下顺序优先选择来源：

1. **官方文档、法规、标准、公告、论文原文**
2. 权威机构、专业出版社、系统综述
3. 高质量新闻媒体与专业数据库
4. 一般二手来源
5. 社交平台、论坛、聚合站（仅作线索）

**优先原始来源。若来源冲突，指出冲突点、时间、可信度差异。**

### 时效性判定规则

凡是**有超过 10% 概率已变化**的信息，先联网核验：

- 新闻、价格、规则、政策
- 产品规格、版本、优惠
- 人物职位、比赛结果
- 门店、餐馆、旅行信息

### 输出格式建议

#### 标准输出结构

1. **结论摘要** — 一句话回答核心问题
2. **关键依据与来源** — 列出支撑结论的证据
3. **逻辑说明** — 简要说明推理过程（可选）
4. **不确定点与边界** — 明确说明不确定的部分
5. **可执行建议** — 下一步行动建议（可选）

#### 引用规则

- 每个关键事实后跟引用
- 不要把所有引用堆在结尾
- 未核验的线索不得伪装成事实

#### 不确定性披露场景

必须显式披露不确定的场景：

- 来源冲突
- 仅有单一非官方来源
- 页面不可访问/抽取失败
- 最新信息可能尚未公开
- 结论依赖推断

### 查询改写模板

每次搜索前，可将原问题改写为多条候选查询：

| 查询类型 | 示例 |
|----------|------|
| 精确查询 | `current CEO of [company]` |
| 召回查询 | `[company] CEO` |
| 官方查询 | `site:[official domain] [company] leadership` |
| 时效查询 | `[topic] 2026 update` |
| 交叉查询 | `[topic] announcement site:[official domain]` |

### 质量自检清单

#### 搜索前
- [ ] 问题是否需要最新信息？
- [ ] 搜索关键词是否准确？

#### 搜索后
- [ ] 关键结论是否有来源支撑？
- [ ] 来源是否足够可信？
- [ ] 是否有更新的来源？

#### 输出前
- [ ] 事实/推断/建议是否分开？
- [ ] 不确定点是否已说明？
- [ ] 输出格式是否清晰？

---

## 与其他技能的协作

| 场景 | 推荐技能 |
|------|----------|
| 深度研究、多平台综合 | `deep-search-research` |
| 复杂页面、JS-heavy、登录态 | `agent-browser` |
| 难抓取网页、反爬绕过 | `scrapling-plus` |
| 社交平台数据（B站/小红书/Twitter） | `opencli-bridge` |
