---
name: quick-web-search
description: Use for web lookups, recent news, official/technical docs, GitHub discovery, Chinese WeChat/Bilibili/Xiaohongshu searches, page reading, or RSS tracking. Automatically route natural-language requests to fast search/read or deep-search-research.
---
# Unified Search v2 — 快查 / 阅读 / RSS

路径示例中的<OpenClaw目录>由Agent替换为当前用户实际绝对路径；以本技能所在目录定位脚本，不要求固定账号或系统目录。
用户只需自然语言提需求；由 Agent 选路、执行、读证据、回答。CLI 是内部入口，不要求用户写参数。

## 主入口与依赖
- 统一入口：本技能 scripts/search.py；与 deep-search-research 共享 scripts/search_core。
- Windows 安装路径：<OpenClaw目录>\skills\quick-web-search\scripts\search.py。
- 已有 Python 3.11 + requests + beautifulsoup4 足够主链；PDF可选pypdf。无需新增付费API、向量服务、浏览器池或WebUI。
- 不默认安装/升级第三方组件，不启动/重启网关；现有浏览器后备只复用明确配置的loopback CDP（默认18800）。
- 脚本不读取/转存cookies，不终止共享浏览器，不依赖OpenCLI扩展；OpenCLI可用时仍可通过opencli-bridge作专业后备。

## Agent 自动执行流程
1. 判断意图：URL阅读→read；明确报告/比较/深入研究→deep-search-research；其余→search。程序auto只是保守兜底，Agent判断优先。
2. 准备查询：保留实体/约束/时间。技术主题补英语变体；主题过宽则做一个聚焦变体，不把中文主题削成AI或强制套GitHub变体。来源默认自动；中文视频流程覆盖wechat,bilibili,xiaohongshu,web。
3. 先执行统一入口；快查默认工作预算30秒，返回已有部分结果。不将目标时延说成已保证的SLA。
4. 需要JS或登录态且返回browser_required：使用OpenClaw内置browser profiles/status，选择已授权且可用profile，再start；按browser-automation技能操作。不凭历史记忆假设登录。CDP不是18800时通过SEARCH_CDP_URL或配置文件指定实际loopback地址。
5. 源错误不是零结果：检查traces、coverage、status。login_required/captcha明确说明；必要的人工决策用OpenClaw ask_user，一次一问、推荐项首列。不绕过验证，也不因后备有索引摘要就宣称原生搜索/全文通过。
6. 挑选相关原文，调用read；搜狗/link提供搜索结果的原始标题作为read --title，由程序在自有临时搜索页唯一匹配并正常点击，research自动传递标题；若匹配不唯一/标题已变，返回article_match_unavailable，不任取其他文章，也不生成跳转签名。读完才形成需要正文支撑的事实。返回body/page_text/pdf_text/transcript/metadata/none各有边界。标题/简介≠字幕，摘要≠全文，网页正文选择器≠全文完整性证明。
7. 回复用中文、逐关键声明挂原始URL，并区分事实/推断/缺口。creator_content可以支撑创作者自身教程内容，不把所有社交内容机械降级为无效；不把任意域名、GitHub仓或developer子域直接当官方。

## 调用例
所有本机命令使用Windows绝对路径；复杂shell按powershell技能落成.ps1。
~~~powershell
py "<OpenClaw目录>\skills\quick-web-search\scripts\search.py" auto "AI 视频制作 工作流 教程"
py "<OpenClaw目录>\skills\quick-web-search\scripts\search.py" search "ComfyUI video workflow" --sources web,github --queries "ComfyUI video tutorial official"
py "<OpenClaw目录>\skills\quick-web-search\scripts\search.py" read "https://docs.searxng.org/admin/installation.html"
py "<OpenClaw目录>\skills\quick-web-search\scripts\search.py" research "对比AI视频制作工作流" --output "<OpenClaw目录>\workspace\outputs\search-research"
py "<OpenClaw目录>\skills\quick-web-search\scripts\search.py" health
~~~
全局选项（action前）：--page 1-10提供分页；小红书原生需滚动、不支持页码，明确降级为公开索引或返回unsupported_pagination。--category news / --time-range day|week|month|year / --language按来源过滤。
其它选项：--fresh跳过结果缓存；--sites严格主机过滤；--budget覆盖预算；--limit输出条数；--queries Agent拟定的变体；--no-browser只用HTTP；--cancel-file指定取消标记；batch接UTF-8 JSON查询数组；research支持--resume checkpoint.json，问题必须相同。

## 结果/证据契约
- schema_version=2.0；status=ok/partial/empty/blocked/cancelled/error；results、coverage、traces、queries、seconds、budget_seconds。
- 结果title/url/canonical_url/platform/provider/query/provenance/relevance/source_type/fetched_at/content_level。实际使用的来源与查询可追踪。
- 排序为词法+意图+覆盖多样性，不声称真实embedding；追踪URL去重、搜狗同标题作者归并、每平台保留相关代表。
- read含text/evidence/locator/hash、作者/时间（获取到才有）、内容类型和warnings。证据段落是抽取内容，不是事实判断。
- report.json/checkpoint.json/report.md是可恢复的材料包，Agent须自行回查冲突、证据缺口与逐声明引用；不把模板报告冒称LLM已完成研究。
- 结果缓存默认900秒/64条，可调；只缓存无警告成功搜索摘要，不缓存读取的登录正文。新闻/价格/版本等时效查询使用--fresh。--output明确保存材料，不写凭据。

## 来源和降级
- web：配置的SearXNG→公开HTTP→现有浏览器Google；过滤不相关与site不匹配结果。
- wechat：搜狗公开文章发现；提供发现标题时用自有临时搜索页正常点击到mp原文，保留正文/公众号名/解析到的发布时间。公开文章样本不需要微信登录；短帖/媒体页只读文字时标为metadata/post_text_only，不冒充媒体正文或视频转写。同一共享profile的搜狗跳转串行处理，避免同时创建多个跳转流程；遇验证码/删除/环境限制如实降级，不保证全文获取率。
- bilibili：公开API→浏览器视频卡片；阅读优先正常页面嵌入的视频元信息，view API受限不阻断player字幕接口。按实际p选择cid，不用第一集替代。接口need_login_subtitle=true明确标记login_required；字幕仅返回实际可读轨道与时间码，否则metadata，并区分未登录/无可访问轨道/接口或字幕文件失败。登录并不保证该集有字幕；没有字幕不做无授权付费ASR。
- xiaohongshu：需要现有登录态的原生搜索；缺登录尝试公开索引发现，discovery_only=true仍需原文验证。
- github：公开API→已配置gh认证，认证信息不进日志/证据。
- 源状态可能随时间、登录和限流变化；当前验证证据见重制任务验收报告，不作永久可用承诺。

## 配置
可选<OpenClaw目录>\search-v2.json；不含必要密钥。
字段：searxng_url、cdp_url、browser、workers(1-3)、language、categories、official_domains(用户/Agent已核实的官方域)、cache_ttl、cache_entries、search_job_budget、read_job_budget、web_providers。
明确官方域仍只是来源身份提示，不保证内容真实。
缺后端照常走已配置后备；health是诊断，不等同真实搜索成功。

## 保留旧能力
旧searxng_search.py、weixin_search.py仍保留为兼容入口，新任务优先search.py。
RSS独立能力保留，订阅文件不迁移、不覆盖：
~~~powershell
py "<OpenClaw目录>\skills\quick-web-search\scripts\rss_fetch.py" fetch "https://hnrss.org/newest" --limit 5
py "<OpenClaw目录>\skills\quick-web-search\scripts\rss_fetch.py" list
py "<OpenClaw目录>\skills\quick-web-search\scripts\rss_fetch.py" monitor
~~~
add/remove修改订阅仅按用户要求；monitor可能更新检查时间，别当只读。常驻监控仍由既有RSS/自动化流程负责，不因本次重制创建新定时任务。
