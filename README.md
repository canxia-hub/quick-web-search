# Quick Web Search v2 · OpenClaw

对话即用的轻量搜索、正文阅读和研究共享底座。Agent按自然语言选择search/read/research，保留RSS与legacy入口。

## 安装与依赖

将本仓库放入OpenClaw的skills/quick-web-search目录，或在技能源码目录运行。Python 3.10+；默认仅需requests与beautifulsoup4：

~~~shell
python -m pip install -r requirements.txt
~~~

Windows可用py替代python。PDF功能另需pypdf；RSS另需feedparser；旧weixin_search.py解析另需lxml，Scrapling仅为其可选后备。按需要安装，不默认启动模型、索引服务或新付费后端。

深研配套技能：[deep-search-research](https://github.com/canxia-hub/deep-search-research)。它依赖本仓库的v2共享底座，可作为skills下的同级目录安装。

## 对话与CLI

用户日常使用自然语言，由Agent选择入口与查询变体。以下CLI示例从本仓库根目录执行：

~~~shell
python scripts/search.py auto "AI 视频制作 工作流 教程"
python scripts/search.py --category news --time-range month search "AI video generation news" --fresh
python scripts/search.py read "https://docs.searxng.org/admin/installation.html"
python scripts/search.py read "https://www.bilibili.com/video/BV14kCvBXEdE/?p=2"
python scripts/search.py research "对比AI视频制作工作流" --output ./research-output
~~~

Agent调用时应解析技能所在目录、使用当前机器的实际路径。完整指引：[SKILL.md](SKILL.md)；配置样例：[search-v2.example.json](search-v2.example.json)。

## 能力

- 统一search/read/research/auto/batch/health入口，批量、页码、时间/新闻意图与严格域名过滤。
- 免费多源召回、查询变体、词法意图排序、来源多样性、稳定文档ID与追踪链接去重。
- 正文/PDF/可访问视频字幕与段落/时间码证据；作者、发布时间按实际获取情况返回。
- 有界worker并发、超时、取消、明确源错误、结果缓存、可恢复研究材料包。
- 默认不依赖embedding、reranker、OpenSearch、WebUI或额外模型服务；词法分数不是可信概率。

## 浏览器与平台条件

先用OpenClaw原生browser工具启动已授权profile；默认复用loopback CDP http://127.0.0.1:18800，其他地址通过SEARCH_CDP_URL或配置指定。不复制cookies、不关闭已有用户标签或共享浏览器。

| 来源 | 路线与边界 |
|---|---|
| 网页/新闻/技术资料 | 可选SearXNG、公开HTTP、已有浏览器后备；失败不是零结果。 |
| 公众号 | 搜狗发现；提供精确标题后唯一匹配并正常点击，等可见正文就绪。公开文章样本不需要微信登录；访问验证/删除/短帖如实分级。 |
| B站 | API或原生浏览器发现；按实际分P CID读取player可访问字幕。当前HTTP412可由浏览器后备处理，但不宣称API恢复。字幕可能要求登录；无轨道则只返回metadata。 |
| 小红书 | 已有登录态的原生搜索和笔记文字；公开索引只是线索，短视频简介不是转写，图片未OCR。 |
| GitHub | 公开API或已有gh认证；仓库来源不自动等于官方资料。 |

字幕按max_chars共同限制text/evidence，预算足够时不固定截断500段；截断明确truncated。研究report.md是证据材料包，最终论断须由Agent回读原文综合。

## 兼容与验证

rss_fetch.py、weixin_search.py与searxng_search.py保留；RSS订阅与状态不迁移。deep-search-research/scripts/research.py复用本底座，旧研究流程保留但不自动运行。

2026-10-04本机真实入口已验证公众号代表正文、XHS图文与短视频简介、B站两个分P完整AI字幕与时间码、原生浏览器检索及技术/PDF/RSS入口。未证明全站成功率、并行全文覆盖或普遍精度提升；免费后端仍可能限流。见[发布验收与限制](docs/SEARCH-V2-ACCEPTANCE.md)。

免费优先指没有新增搜索/抓取API费用，不意味着当前Agent推理免费。历史参考见[CHANGELOG.md](CHANGELOG.md)。
