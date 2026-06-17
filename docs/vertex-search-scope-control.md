# Vertex AI 搜索范围控制 — 能力边界 & shinkai 选型

> **TL;DR** — Grounding with Google Search(我们现在用的)**不支持**任何结构化搜索范围控制;真正能控制范围的是 **Agent Search**(原名 Vertex AI Search),两者是不同产品、不同 API、不同计费,不要混淆。本文档锁定 2026-06-17 的官方文档口径,作为后续做 SEC 一手资料检索的设计前提。

## 1. 两个产品的根本区别

| | **Grounding with Google Search** | **Agent Search**(原 Vertex AI Search) |
|---|---|---|
| 我们用没用 | ✅ 已用于 `web_search` 工具 | ❌ 还没接 |
| 后端 | 公开 web,Google 自己跑搜索 | 自建 data store(网站 / GCS / BigQuery / etc.) |
| API | Gemini `generateContent` 里的 `tools: [{google_search: {}}]` | Discovery Engine API(`TargetSite`、`Document`) |
| 范围控制 | ❌ **零配置字段** | ✅ INCLUDE / EXCLUDE URL 模式 |
| 时效控制 | ⚠️ 只能 prompt 软引导 | ✅ 可按 metadata 过滤(publication_date 等) |
| 域名验证 | 不需要 | ⚠️ Advanced indexing 需要 GSC 域名验证 |
| 计费 | ~$0.04 / search | 存储 + 查询双向计费 |
| 适用场景 | 通用 web 趋势、新闻发现 | 自己拥有 / 可验证的语料(SEC、内部 PDF) |

## 2. Grounding with Google Search — 没办法控制范围

官方文档(`ai.google.dev/gemini-api/docs/google-search` + `docs.cloud.google.com/vertex-ai/.../grounding-with-google-search`)实证:

```json
{
  "contents": [{"role": "user", "parts": [{"text": "..."}]}],
  "tools": [{"google_search": {}}]
}
```

`google_search` 工具的 body 就是空对象 `{}`。**没有**任何下列字段:

- ❌ `siteSearch` / `allowed_domains` / `blocked_domains`
- ❌ `dateRestrict` / `timeRange`
- ❌ `language` / `country` / `region`
- ❌ `safeSearch`(注:CSE 之前有,grounding 没有)

Gemini 自己决定怎么搜、用哪些 region、读哪些站点 — 调用方完全不可控。

### 2.1 唯一的"软"范围引导

shinkai 现在用的就是软引导:

- **`date_restrict`**(`d7` / `m6` / `y2`):`market_utils/search/vertex_grounding.py::_date_restrict_phrase` 把它翻译成自然语言塞 prompt(`"from the past 7 days"`),Gemini "尽量"遵守
- **`topic="news"`**:同样只是 prompt 里加 `" news items"`
- **`region`**:参数还在签名上,但实现里直接 `del region`,Gemini 自己定

### 2.2 如果要加"软"域名引导(轻量级方案)

不改 `market-utils`、不引入新产品,**两步可落地**:

1. **Prompt 端引导** — `_pass1_search` 的 prompt 拼一行:`"Prefer results from these publishers: sec.gov, bloomberg.com, reuters.com, ft.com, wsj.com."`
2. **Python 端 whitelist 兜底** — `_pass2_structure` 返回后,用 `_domain_of(url)` 做白名单/黑名单过滤,Gemini "叛逃"的结果直接丢

代价几乎为零;不能 100% 保证(Gemini 偶尔会塞 SeekingAlpha 之类),所以 whitelist 兜底是必须的。

## 3. Agent Search — 真正的范围控制

### 3.1 API 形状

创建 website data store 时,逐条 `TargetSite`:

```python
from google.cloud import discoveryengine_v1 as de

client = de.SiteSearchEngineServiceClient()
data_store_path = client.data_store_path(project, location, data_store_id)
engine_path = f"{data_store_path}/siteSearchEngine"

# INCLUDE
client.create_target_site(
    parent=engine_path,
    target_site=de.TargetSite(
        provided_uri_pattern="sec.gov/*",
        type_=de.TargetSite.Type.INCLUDE,
    ),
)

# EXCLUDE
client.create_target_site(
    parent=engine_path,
    target_site=de.TargetSite(
        provided_uri_pattern="sec.gov/cgi-bin/browse-edgar*",
        type_=de.TargetSite.Type.EXCLUDE,
    ),
)
```

Console 里对应字段名是 **"Sites to include"** / **"Sites to exclude"**。

### 3.2 重要规则(踩坑预防)

- ✅ **通配符**:`example.com/docs/*` 合法
- ⚠️ **EXCLUDE 优先于 INCLUDE**:`include example.com/docs/*` + `exclude example.com` → 索引为空(EXCLUDE 杀掉了所有)。规划时把 EXCLUDE 写小、INCLUDE 写大。
- ⚠️ **不要带 `http://` / `https://` 前缀**,API 会报错
- ⚠️ **Advanced indexing 需要域名验证**(走 Google Search Console 那套 TXT / Meta tag 流程):你要拥有 / 能管理这个域才能开。
- ⚠️ **Basic indexing 不需要域名验证**,但功能受限(没有 metadata boost、generative answer 等)
- ⚠️ 结果:**第三方域(bloomberg.com、reuters.com)走不了 Agent Search**,因为我们不拥有这些域 — 这是这条路线的硬上限。

### 3.3 范围之外的过滤

INCLUDE/EXCLUDE 是入索引前的粗筛。查询时还可以:

- **metadata 过滤**:`filter="publication_date >= \"2026-01-01\""`(需要 ingest 时带上字段)
- **boost**:按 freshness / metadata 加权,不丢结果但调排序
- **结构化字段**:对 BigQuery / 自定义 schema data store 可以 SQL-like where

## 4. shinkai 的实际选型矩阵

| 场景 | 后端 | 范围控制方式 |
|---|---|---|
| Mode B 公共面发现(theme → 公司) | `google_search` grounding | Prompt 引导 + Python whitelist(SEC / 主流财经) |
| 新闻 / 趋势刷新 | `google_search` grounding | `date_restrict` + topic="news" |
| **SEC 10-K / 10-Q 一手资料** | **Agent Search**(`sec.gov/*`) | INCLUDE = `sec.gov/Archives/edgar/data/*`,EXCLUDE = `sec.gov/cgi-bin/*` |
| 分析师 PDF / 内部研究文档 | Agent Search(GCS unstructured) | 用文件夹组织,metadata 加 source/date |
| 第三方付费数据(Bloomberg API 等) | 走对应 vendor SDK | 不要硬塞 Agent Search |

**第一性原则**:Agent Search 适合你**拥有 / 能拿到原始字节**的语料;`google_search` grounding 适合**只能读公开 web**的语料。第三方域(bloomberg.com 等)只能走 grounding 软引导 + whitelist 兜底,这是产品边界,不是配置问题。

## 5. 后续如果要接 Agent Search

实施路径(等到 Mode A 需要硬控 SEC 范围时再做,V0 不上):

1. 在 `shinkai-research` 项目里启用 Discovery Engine API
2. SA 加 `roles/discoveryengine.editor`
3. 新建 website data store,collection 名 `sec-primary`,INCLUDE `sec.gov/Archives/edgar/data/*`
4. 走 GSC 验证 `sec.gov`(注:这个我们没法验证,SEC 不会给我们域名权限)
5. → **改走 Basic indexing**(无验证,功能受限),或
6. → **直接用 EDGAR submissions endpoint 抓 10-K JSON,自己 ingest 进 unstructured data store**(更可控,推荐)

`tools/ticker_validator.py::SEC_USER_AGENT` 已经具备走 EDGAR 的能力,Agent Search 集成本质上是"在 EDGAR 抓取之上加一层 indexed full-text retrieval",和现在的 `sec_filings` 工具是补集,不是替代。

## 6. Sources(官方文档,2026-06-17)

- [Grounding with Google Search — Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/grounding/grounding-with-google-search)
- [Grounding with Google Search — Gemini API](https://ai.google.dev/gemini-api/docs/google-search) — 实证 `google_search` 配置为空对象
- [Create a search data store — Agent Search](https://docs.cloud.google.com/generative-ai-app-builder/docs/create-data-store-es) — `TargetSite` API 形状
- [Turn on advanced website indexing — Agent Search](https://docs.cloud.google.com/generative-ai-app-builder/docs/turn-on-advanced-indexing) — 域名验证要求
- [Site search from Vertex AI — overview](https://cloud.google.com/use-cases/site-search)
