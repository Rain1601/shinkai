# Vertex AI 搜索范围控制 — 能力边界 & shinkai 选型

> **TL;DR**(2026-06-18 修订)— Grounding with Google Search 现在**支持 `exclude_domains` 黑名单**(2026 年新增),但**仍然没有原生 allowlist**;真正的 allowlist 走 **Agent Search**(原名 Vertex AI Search)。关键修正:**Agent Search basic indexing 不需要域名验证**,可以指向 WSJ / Bloomberg / Reuters 这种第三方域 — 之前文档说"第三方域走不通"是错的。

## 修订记录

- **2026-06-17 v1**:初版,基于"grounding 完全无范围控制 + Agent Search 第三方域需验证"两个错误假设。
- **2026-06-18 v2**:纠正两处:
  - grounding 新增 `exclude_domains` 字段(Python SDK `GoogleSearch(exclude_domains=[...])`)
  - Agent Search basic indexing 走第三方域**不需要 GSC 验证**;只有 advanced indexing 需要
- 同时新增第三方 grounding 后端(Exa、Parallel)的说明。

## 1. 三种搜索后端对比

| | **Grounding · Google Search** | **Agent Search · basic indexing** | **Agent Search · advanced indexing** |
|---|---|---|---|
| 我们用没用 | ✅ `web_search` 工具 | 计划中(本次新增) | 计划中(SEC 一手) |
| 后端 | 公开 web,Google 自跑 | 你给的 URL 模式列表,Google 抓 | 同左 + AI 摘要 / 跟进 |
| **域名 allowlist** | ❌ 仍无 | ✅ 最多 50 个 URL pattern | ✅ 同左 |
| **域名 blacklist** | ✅ `exclude_domains` ← **新** | ✅ EXCLUDE TargetSite | ✅ 同左 |
| 拥有域名要求 | 无 | **无** ← 关键纠正 | 需 GSC 验证 |
| AI 摘要 / 跟进 | grounding 自带 | ❌ 无 | ✅ 有 |
| 计费 | ~$0.04 / search | 存储 + 查询 | 存储 + 查询(更贵) |
| 适用场景 | 通用 web,加黑名单剔噪 | **WSJ / Bloomberg / Reuters 这种第三方质量站** | 自有 / 可验证语料(自家产品、SEC.gov 这种公共域) |

> 此外 Google 还新出了 **Grounding with Exa** 和 **Grounding with Parallel** 两个替代 grounding 后端,都带 `EXCLUDE_DOMAINS`。shinkai 暂不考虑,记一笔作为备选。

## 2. Grounding with Google Search — 有 `exclude_domains`,无 allowlist

### 2.1 新增的 `exclude_domains` 字段

2026 年 Vertex AI 的 google_search 工具新增了 `exclude_domains: list[str]` 配置:

```python
# Python google-genai SDK
Tool(google_search=GoogleSearch(exclude_domains=["holdingschannel.com", "kucoin.com"]))
```

```json
// REST body
{
  "contents": [{"role": "user", "parts": [{"text": "..."}]}],
  "tools": [{"google_search": {"exclude_domains": ["holdingschannel.com", "kucoin.com"]}}]
}
```

**Google 在搜索前就跳过这些域名**,不是事后过滤,所以完全不消耗 grounding 分位。

仍然没有的字段(社区在催 allowlist,Google 暂未加):

- ❌ `siteSearch` / `allowed_domains` / `include_domains`
- ❌ `dateRestrict` / `timeRange`(只能 prompt)
- ❌ `language` / `country` / `region`
- ❌ `safeSearch`

### 2.2 软引导仍然有用(锦上添花)

`exclude_domains` 是结构化的,但要"偏向 SEC / Bloomberg / Reuters"还是只能软引导:

- **prompt 端**:harness 的 `_evidence_query` / `_contradiction_query` 已经加了 `_SOURCE_QUALITY_HINT`(commit `ae5ae49`)
- **`date_restrict`**(`d7` / `m6` / `y2`):仍然是 prompt 自然语言塞入
- **Python 端 noise filter + dedup + aggregator 降权**:`tools/source_filters.py`(`6295520`)+ `source_reliability_score(is_aggregator=...)`(`25ec039`)

### 2.3 `site:` 操作符不能用

实测把 `site:wsj.com OR site:bloomberg.com` 塞进 query 给 Vertex grounding → **0 结果**。Gemini 的 `google_search` 工具不像浏览器 Google 那样吃这个语法,直接判空。

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
- ✅ **Basic indexing 不需要域名验证** ← **关键事实(2026-06-18 纠正)**:可以指向 wsj.com / bloomberg.com / reuters.com 等任何第三方域,但需要在 console 里**显式关掉 Advanced indexing**。功能差异是少了 AI 摘要 / follow-up — shinkai 本来就在 harness 那边做摘要,这些 grounding 自带的功能不重要。
- ⚠️ **Advanced indexing 才需要域名验证**(GSC 的 TXT / Meta tag):走 advanced 时你要拥有 / 能管理这个域。
- ✅ **第三方域 allowlist 是这条路线的核心价值**:WSJ / Bloomberg / Reuters / CNBC / FT 这种最高质量站,Mode A 公司深研的"硬目标"。最多 **50 个 URL pattern / data store**。

### 3.3 范围之外的过滤

INCLUDE/EXCLUDE 是入索引前的粗筛。查询时还可以:

- **metadata 过滤**:`filter="publication_date >= \"2026-01-01\""`(需要 ingest 时带上字段)
- **boost**:按 freshness / metadata 加权,不丢结果但调排序
- **结构化字段**:对 BigQuery / 自定义 schema data store 可以 SQL-like where

## 4. shinkai 的实际选型矩阵(2026-06-18 修订)

| 场景 | 后端 | 范围控制方式 | 状态 |
|---|---|---|---|
| Mode B 公共面发现(theme → 公司) | `google_search` grounding | **`exclude_domains=NOISE_DOMAINS`** + prompt 引导 + Python aggregator 降权 | 部分上(R1+R2+source_filters),exclude_domains 待接 |
| 新闻 / 趋势刷新(theme ingestion) | `google_search` grounding | 同上 + `date_restrict` | 同上 |
| **Mode A 公司深研 — 高质量第三方报道** | **Agent Search basic indexing** | INCLUDE `wsj.com/* bloomberg.com/* reuters.com/* cnbc.com/* ft.com/*` | **新增能力,本次实施** |
| **SEC 10-K / 10-Q 一手资料** | **Agent Search basic indexing** | INCLUDE `sec.gov/Archives/edgar/data/*` 或直接走 EDGAR API | 仍未上,Mode A 启动时再做 |
| 分析师 PDF / 内部研究文档 | Agent Search GCS unstructured | 用文件夹组织,metadata 加 source/date | 还远 |

**第一性原则修订版**:`google_search` grounding 适合**广撒网 + 黑名单剔噪音**;Agent Search basic indexing 适合**白名单锁定高质量源**(无论你是否拥有那些域)。两条路线在 shinkai 是互补,不是替代关系。

## 5. 实施路径

### 5.1 grounding 加 `exclude_domains`(Step 2-3,小)

- `market-utils` 的 `VertexGroundingSettings` 加 `exclude_domains: list[str]`
- `VertexGroundingStrategy._pass1_search` 透传到 body `tools[0].google_search.exclude_domains`
- shinkai 端 `bridge_env_to_market_utils` 把 `NOISE_DOMAINS` 透传过去
- 同时保留 `tools/web.py` 的 Python 端 noise filter(兜底,防 `.net` vs `.com` 漏)

### 5.2 Agent Search premium data store(Step 4-5,中)

一次性 setup(`scripts/provision-premium-data-store.py`,需 admin 手动跑):

1. 启用 Discovery Engine API
2. SA 加 `roles/discoveryengine.editor`
3. 新建 website data store `premium-news`
4. **关闭 Advanced indexing**(关键 — 否则 wsj.com 这种第三方域要求验证)
5. TargetSite INCLUDE:`wsj.com/*` `bloomberg.com/*` `reuters.com/*` `cnbc.com/*` `ft.com/*` `nytimes.com/*` `economist.com/*`(7-10 个起步,留扩展空间到 50)
6. 记下 `data_store_id`,写进 `SHINKAI_AGENT_SEARCH_DATA_STORE_ID`

代码侧:

- `market-utils` 新 strategy `AgentSearchStrategy`
- `shinkai_api/tools/web.py` 暴露 `strategy="agent_search_premium"`
- harness Mode A 走深研时切到这条路径(后续单独 commit)

### 5.3 SEC 一手资料(后续,不在本次实施)

`sec.gov` 走 Agent Search basic indexing 不需要验证(SEC 不会给我们 GSC 权限,但 basic 不需要),或者继续用现有 `sec_filings` 工具走 EDGAR API。两条路都可行,等 Mode A 真正接触 SEC 文档时再决定。

## 6. Sources

- [google_search tool with exclude_domains — Vertex AI SDK sample](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-tools-google-search-with-txt) — 2026 新增字段,实证 `GoogleSearch(exclude_domains=[...])` 形状
- [Grounding with Google Search — Gemini API](https://ai.google.dev/gemini-api/docs/google-search) — google_search 主页
- [Migrate from CSE Site Restricted to Agent Search](https://docs.cloud.google.com/generative-ai-app-builder/docs/migrate-from-cse) — 旧 CSE 的官方迁移路径,**确认 basic indexing 不需要验证**
- [Create a search data store — Agent Search](https://docs.cloud.google.com/generative-ai-app-builder/docs/create-data-store-es) — `TargetSite` API 形状
- [Turn on advanced website indexing — Agent Search](https://docs.cloud.google.com/generative-ai-app-builder/docs/turn-on-advanced-indexing) — advanced indexing 的域名验证要求
- [Grounding with Exa web search (alt backend)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-exa) — 替代 grounding 后端,带 EXCLUDE_DOMAINS
- [Grounding with Parallel web search (alt backend)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-parallel) — 另一个替代,同上
