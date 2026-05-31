# Shinkai · Engineering Framework v0

> **时间**:2026-05-27
> **状态**:V0 工程框架(具体技术栈 + 服务拓扑 + 交互设计原则)
> **取代**:`alignment-v2.md` §11 "Middle Layer form" 和 §13 关于部署/客户端的默认值

本文档定义:
- 完整的服务拓扑(Web + iOS + 后端 + Agent)
- 每一层的技术栈选择
- **API 契约**(3 个客户端共消费,最重要)
- **交互设计原则**(用户明确强调:交互至上)
- 分阶段交付计划

---

## 0. 关键判断:从"CLI 优先"转向"API 优先"

之前 B+C 设计默认"V0 = CLI + 极简 Web 观察"。用户明确 web + iOS 双客户端,**这是一个根本性方向调整**:

| 之前 | 现在 |
|------|------|
| CLI 为主,Web V1 | **Web + iOS 都是 V0 客户端** |
| 中间层 = CLI 入口 | **中间层 = HTTP/WebSocket API** |
| 单进程脚本风格 | **服务化(FastAPI + worker)** |
| 部署 = 本地跑 | **部署 = 容器化后端 + Web 托管 + iOS 上架** |

**这意味着 V0 从一开始就是一个真实的产品后端,不是个 demo 脚本。**

---

## 1. 整体拓扑

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  Web Client      │  │  iOS Client      │  │  CLI (dev only)  │
│  Next.js + TS    │  │  SwiftUI         │  │  Python click    │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
         │                     │                     │
         └─────────┬───────────┴───────────┬─────────┘
                   │                       │
                   ▼                       ▼
       ┌─────────────────────────────────────────────┐
       │  Shinkai API Gateway · FastAPI (Python)     │
       │  REST + WebSocket + SSE                     │
       │  Auth · Rate-limit · Request validation     │
       └────────────────────┬────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
    ┌──────────────────┐       ┌──────────────────────┐
    │  Run Service     │       │  Read Service        │
    │  控制 lifecycle   │       │  查询 + 渲染          │
    └────────┬─────────┘       └─────────┬────────────┘
             │                           │
             ▼                           ▼
    ┌─────────────────────────────────────────────────┐
    │  Agent Worker Pool                              │
    │  (asyncio tasks 跑 Agent Loop)                   │
    │  · LLMRouter · GraphStore · ToolBox             │
    └────────┬───────────────────────┬────────────────┘
             │                       │
             ▼                       ▼
    ┌────────────────┐      ┌─────────────────────────┐
    │  Event Bus     │      │  Persistence            │
    │  in-process    │      │  · Postgres (run/graph) │
    │  → Redis (V1)  │      │  · S3/local (artifacts) │
    └────────┬───────┘      └─────────────────────────┘
             │
             ▼
   (events 通过 SSE/WS 推回客户端)
```

**关键设计**:**模块化单体(modular monolith)**起步,V1 再按需拆服务。早拆是过度设计;晚拆是技术债。V0 单进程内逻辑分模块清晰,接口契约写好,拆分时阻力最小。

---

## 2. 后端架构(Python)

### 模块划分

V0 单一 Python 服务,内部模块:

```
shinkai/
├── api/             FastAPI app(所有 HTTP/WS 入口)
├── kernel/          Run lifecycle, EventBus, CheckpointGateway, AuditLog
├── agent/           Agent loop(run / item / step)
├── llm/             LLMRouter + provider clients
├── tools/           8 个工具实现
├── graph/           GraphStore + Pydantic types
├── checklist/       Checklist loader + 推进逻辑
├── workers/         async 任务调度
└── infra/           db, cache, storage 客户端
```

### 技术栈选择

| 关注点 | 选择 | 原因 |
|--------|------|------|
| HTTP/WS 框架 | **FastAPI** | async 原生、Pydantic 类型、自动 OpenAPI |
| ASGI 服务器 | **Uvicorn** | FastAPI 标配 |
| 后台任务 | **asyncio + Postgres advisory lock**(V0)→ **arq + Redis**(V1) | V0 不引 Redis;V1 横向扩展时迁移 |
| 数据库 | **Postgres + JSONB** | run 状态 + graph 都用 JSONB 存,灵活且可查 |
| 迁移 | **Alembic** | 标准 SQLAlchemy |
| 对象存储 | 本地 FS(V0) → S3(V1) | 原始 filings、报告产物 |
| 实时 | **SSE(单向) + WebSocket(双向)** | SSE 简单适合观察;WS 用于交互 |
| 配置 | **pydantic-settings + .env** | 类型化、环境感知 |
| Auth | **JWT(access + refresh)** | 移动端友好 |
| 推送 | **APNs(iOS)+ Web Push** | 原生通道 |
| 日志 | **structlog** | 结构化 JSON |
| 错误追踪 | **Sentry** | 业界标配 |

### Postgres schema(主要表)

| 表 | 字段要点 |
|---|---------|
| `users` | id, email, hashed_password, created_at |
| `runs` | id, user_id, mode, anchor, status, parent_run_id, scoping JSONB, budget JSONB |
| `checkpoints` | id, run_id, section_id, status, decision JSONB, raised_at, released_at |
| `events` | id, run_id, type, data JSONB, ts(按 run_id 分区) |
| `graphs` | run_id, snapshot_version, payload JSONB(完整图谱) |
| `graph_diffs` | run_id, ts, diff JSONB(增量变化,渲染前端用) |
| `entities_index` | canonical_name, external_ids JSONB, run_refs(跨 run 实体合并) |
| `push_subscriptions` | user_id, platform, device_token, active |

### Agent worker 模型

- 每个 Run = 一个 asyncio task
- V0 单 Python 进程,concurrency 限制可配(默认 4)
- 崩溃恢复:每个 action 前先写 event,重启后从最新 event 重建状态
- Agent task 生命周期 60-120 分钟,**不受客户端连接影响**(SSE 断了不影响 Agent 继续跑)

---

## 3. Agent Framework(从 B+C 设计精化)

### 服务化接口

Agent Worker 暴露给 Kernel 的接口:

```python
class AgentWorker:
    async def start(self, run_spec: RunSpec) -> RunID
    async def pause(self, run_id: RunID) -> None
    async def resume(self, run_id: RunID) -> None
    async def abort(self, run_id: RunID) -> None
    async def inject(self, run_id: RunID, signal: Injection) -> None
    async def release_checkpoint(self, checkpoint_id, decision) -> None
    # 内部通过 EventBus 发事件,不直接返回数据
```

### Run 状态机

```
   created ──start──▶ running ◀──resume── paused
                      │   ▲                ▲
                      │   │                │
                      │   └──release()─────┤
                      │                    │
                      ├──checkpoint──▶ awaiting_review
                      │
                      ├──completed
                      ├──failed
                      └──aborted
```

### 崩溃安全性

- **Action 之前**写 event(`tool.calling`),**action 之后**写 event(`tool.completed` / `tool.failed`)
- 重启时:加载最新 event,如果是 `*.calling` 状态,根据 idempotency 决定 retry 或 mark_failed
- Graph 用 Postgres 事务原子更新

---

## 4. API 契约(最重要的一节)

3 个客户端同消费,这是**最 expensive 错误的地方**。先做对。

### 通用规范

- REST 用于资源,WebSocket 用于交互式 session,SSE 用于单向 push
- JSON 全程(后端 Pydantic / 前端 zod / iOS Codable)
- Auth:JWT Bearer header
- 错误:RFC 7807 Problem Details
- 版本:`/api/v1/` 前缀;v2 并存策略

### 核心端点

```
═══ Auth ═══
POST   /api/v1/auth/login              {email,pw}    → {access,refresh}
POST   /api/v1/auth/refresh            {refresh}     → {access}

═══ Runs ═══
POST   /api/v1/runs                    {mode,scope}  → {run_id,status}
GET    /api/v1/runs                    list runs(分页 + 筛选)
GET    /api/v1/runs/{id}               run 摘要 + 当前状态
POST   /api/v1/runs/{id}/pause
POST   /api/v1/runs/{id}/resume
POST   /api/v1/runs/{id}/abort
POST   /api/v1/runs/{id}/inject        {kind,payload}

═══ Checkpoints ═══
GET    /api/v1/runs/{id}/checkpoints   list (pending + 历史)
POST   /api/v1/checkpoints/{id}/release {decision,comments,edits}

═══ Graph ═══
GET    /api/v1/runs/{id}/graph         完整 graph
GET    /api/v1/runs/{id}/graph/subgraph?focus={node_id}&hops=N
GET    /api/v1/runs/{id}/report        渲染后的 Markdown
GET    /api/v1/runs/{id}/report.json   机器可读 graph

═══ Realtime ═══
GET    /api/v1/runs/{id}/events        SSE 流(单向观察)
WS     /api/v1/runs/{id}/session       WebSocket(双向,review 用)

═══ Push ═══
POST   /api/v1/push/subscribe          {platform,device_token}
DELETE /api/v1/push/subscribe/{id}
```

### Event payload(SSE/WS 共用)

```typescript
{
  event_id: string;
  run_id: string;
  timestamp: string;        // ISO 8601
  type: string;             // 见 B+C 文档的 event 类型表
  data: object;             // type-specific
  running_meta: {
    tokens_used: number;
    cost_usd: number;
    wall_time_sec: number;
    current_section: number;
    current_item: string;
  };
}
```

### OpenAPI 自动生成

FastAPI 自动生成 OpenAPI 3.1 spec → 前端用 `openapi-typescript` 生成 TS 类型 → iOS 用 `swift-openapi-generator` 生成 Swift 类型。**三端共享同一份类型定义,从源头消除契约不一致**。

---

## 5. Web 前端(Next.js)

### 技术栈

| 维度 | 选择 |
|-----|------|
| 框架 | **Next.js 16(App Router)** |
| 语言 | TypeScript |
| 样式 | **Tailwind CSS** + **shadcn/ui**(组件库) |
| 数据获取 | **TanStack Query**(HTTP 缓存) |
| 状态管理 | **Zustand**(轻量;不引 Redux) |
| SSE | 原生 `EventSource` |
| WebSocket | 原生 `WebSocket` 或 `socket.io-client` |
| 图谱可视化 | **React Flow** 或 **Cytoscape.js** |
| Markdown | **react-markdown** + **rehype-highlight** |
| 表单 | **react-hook-form** + **zod** |
| Auth | JWT(localStorage)+ Bearer header |
| 部署 | **Vercel**(平台契合) |

### 页面结构

```
/                      Landing(已登录跳 /runs)
/login                 登录
/runs                  Runs 列表(过滤 / 搜索 / 状态)
/runs/new              新建 run(Mode A / Mode B 切换 + Scoping 表单)
/runs/[id]             ★ 活跃 run 仪表盘
  ├─ Live event stream(左侧时间流)
  ├─ Graph viewer(中央可视图谱)
  ├─ Progress bar(顶部 section 进度)
  └─ Action panel(右侧 pause/inject/edit)
/runs/[id]/review      ★ Checkpoint 审阅(阻塞时强制跳转)
/runs/[id]/report      最终报告(渲染 markdown + 下载 JSON)
/settings              账户 / 通知偏好 / 预算上限
```

### 关键组件

| 组件 | 职责 |
|------|------|
| `RunDashboard` | 主活跃视图,订阅 SSE,coordinate 子组件 |
| `EventStreamFeed` | Twitter 式时间流,展示 Agent 的思考 + tool calls |
| `GraphViewer` | 渲染研究图谱(React Flow);支持 focus / zoom / filter |
| `SectionProgress` | 顶部进度条,显示 checklist 完成进度 |
| `CheckpointReviewer` | ★ **关键交互**:展示子图 + critic 反馈 + 一键决策 |
| `InjectionDialog` | 用户主动 push 信息给 Agent |
| `ReportRenderer` | 从 graph 渲染最终 markdown 报告 |

---

## 6. iOS 前端(SwiftUI)

### 技术选型决策:**原生 SwiftUI**

| 选项 | 优 | 劣 | V0 选择 |
|------|---|---|---------|
| **SwiftUI 原生** | 原生体验、动画流畅、APNs/通知集成最佳、长期维护性好 | 单独代码库;需要 iOS 技能 | ✅ |
| React Native(Expo) | 与 web 部分代码共享、初期快 | 原生感差;复杂交互(sheet / animation)调优麻烦 | ✗ |
| Web 包壳 | 最快 | 不是真 app;Apple 可能拒;UX 差 | ✗ |

**用户明确说"交互很重要" → 原生 SwiftUI 是唯一正确选项。**

### 技术栈

| 维度 | 选择 |
|-----|------|
| UI | **SwiftUI**(iOS 17+) |
| 响应式数据流 | **Combine** |
| 网络 | `URLSession`(HTTP) + `URLSessionWebSocketTask`(WS) |
| SSE | 自定义客户端或 `EventSource` 库 |
| 推送 | **APNs**(后端通过 push subscription 发) |
| 凭证存储 | **Keychain** |
| 离线缓存 | **CoreData**(V0 optional;查看历史报告用) |
| 序列化 | `Codable`(从 OpenAPI 生成类型) |

### V0 iOS 屏幕(最小集)

1. **Login**
2. **Runs list**
3. **Run detail**(实时观察,SSE 订阅)
4. **★ Checkpoint review**(优先级最高 — 移动端 UX 关键)
5. **Report viewer**(markdown 渲染)
6. **Settings**(推送开关、账户)

**V0 iOS 不做"启动新 run"** — 大概率用户在 web 启动,iOS 用于"观察 + 审阅 + 看报告"。这是合理的劳动分工,也压缩 V0 iOS 范围。

### iOS 特有交互

- **Checkpoint 推送**:Agent 到达 checkpoint → 后端通过 APNs 发推送 → 用户点击进入 review
- **后台 SSE 限制**:iOS 不允许后台长连接 → 用 APNs 作为"唤醒信号",app 前台时重新订阅 SSE
- **离线查看历史报告**:CoreData 缓存(可选 V0)

---

## 7. 交互设计原则(用户特别强调)

把交互升级为一等公民,记下五条原则:

### IP-1 · Live by default(实时优先,禁止轮询)
所有"活跃视图"订阅 SSE/WS。绝不做 `setInterval` 轮询。

### IP-2 · Checkpoint 是神圣时刻
checkpoint UX 是 V0 最高质量的交互:
- 手机收推送、Web 切换专门页面(配色 / 呼吸动画提示状态变化)
- 子图**默认折叠**,展示摘要 + critic 重点;展开看细节
- 一键 **Approve / Reject / Inject** 三种决策
- Review 截图就是 shinkai 的"产品照片"

### IP-3 · 让人能看见 Agent 的思考
Live event stream 不是开发者日志,是**一等 UI**:
- Thought: "查找 FY23 R&D 支出..."
- Tool: "调用 SEC fetch · AAPL 10-K"
- Finding: "R&D = $26.3B(Evidence#42)"
- Graph delta:新增节点带 diff 高亮

用户像看视频一样看 Agent 工作 — 有吸引力,不枯燥。

### IP-4 · 跨设备无缝接力
状态全在服务端,客户端是无状态视图。Web 启动 → 手机审阅 → Web 收尾,丝滑。

### IP-5 · Mobile-first checkpoint review
checkpoint 审阅页面**手机优先**优化(竖向滚动、大按钮、紧凑图谱)。桌面是手机版的丰富版本,不是反过来。

---

## 8. 横切关注

### Auth
- JWT:access(15 min)+ refresh(30 d)
- iOS:Keychain 存 token
- Web:HTTP-only cookie 或 localStorage(看安全偏好)
- 2FA(TOTP)放 V1

### Observability(内部用,不是给最终用户)
- **OpenTelemetry** traces — Agent loop 的 trace 对调试至关重要
- **Sentry** — 错误追踪
- **每个 run 的成本面板** — LLM 账单可以飙,必须可见

### 部署拓扑

| 组件 | 部署 |
|------|------|
| Backend(FastAPI) | **不能用 Vercel Functions**(超过函数时长上限);用 **Fly.io / Railway / Render / 自托管 Docker** |
| Web frontend | **Vercel**(完美契合) |
| iOS app | TestFlight V0 → App Store V1 |
| Postgres | 托管(**Neon** / Supabase / RDS) |
| 对象存储 | 托管 S3 兼容(R2 / S3) |
| Redis(V1) | Upstash / Redis Cloud |

**注意**:LLM Agent 的 60-120 分钟长跑**不适合任何 serverless function**,必须容器宿主。

---

## 9. 技术栈一图

| 层 | 选择 |
|---|------|
| Web 前端 | Next.js 16 + TS + Tailwind + shadcn/ui + TanStack Query + Zustand + React Flow |
| iOS 前端 | SwiftUI + Combine + URLSession + APNs + Keychain |
| 后端 API | FastAPI + Uvicorn + Pydantic + structlog |
| Agent | asyncio + LLMRouter(AIHubMix)+ 8 tools + GraphStore(Postgres JSONB) |
| 数据 | Postgres + JSONB + S3 兼容存储 |
| 实时 | SSE(单向)+ WebSocket(双向) |
| Auth | JWT(access + refresh) |
| 推送 | APNs / Web Push |
| 部署 | 容器宿主(后端)+ Vercel(web)+ TestFlight/App Store(iOS) |

---

## 10. 分阶段交付(realistic timeline)

| Phase | 内容 | 估时 |
|-------|------|------|
| **0 · Foundation** | 后端骨架(FastAPI + Postgres + auth) + LLMRouter + GraphStore + 1 个工具 + "hello world" Agent | 1-2 周 |
| **1 · Mode A 垂直切片** | 全 8 个工具 + Mode A Section 1(1.1-1.5)端到端 + Web 列表/仪表盘 + SSE 事件流 | 2-3 周 |
| **2 · Full Mode A** | Section 2-8 + critic + checkpoint UI(Web)+ 首个完整 Mode A run 可交付 | 2-3 周 |
| **3 · Mode B** | Discovery checklist + subrun orchestration + 综合发现报告 | 2-3 周 |
| **4 · iOS** | SwiftUI app(登录 + runs list + detail + ★checkpoint review + report)+ APNs + TestFlight | 2-3 周 |
| **5 · 生产化** | 多用户 + 成本面板 + memory consolidation + App Store 上架 | 2-4 周 |

**总计:~3-4 个月到完整 V0(含 iOS)**

---

## 11. 等用户决策的 5 个开放问题

| # | 决策 | 我推荐 | 备注 |
|---|------|-------|------|
| 1 | iOS 技术栈 | **原生 SwiftUI** | "交互至上"硬性要求 |
| 2 | 后端部署 | **Fly.io 或 Railway**(容器) | Vercel Functions 无法承载长跑;Web 仍 Vercel |
| 3 | 数据库 | **Neon Postgres**(托管) | 标准、有免费层、JSONB 完美 |
| 4 | iOS V0 范围 | **只做"观察 + 审阅"**(启动新 run 留 web) | 削减范围;符合典型使用场景 |
| 5 | 首版 auth | **邮箱 + 密码 + JWT**(Google OAuth 留 V1) | 简单标准 |

---

## 12. 留待 V1+

- 多服务拆分(API 与 Agent worker 分进程)
- arq / Celery + Redis 真正 worker 队列
- WebSocket 升级为标准长连接(SSE 不足时)
- App Store 上架 + 推送优化
- 多用户 + 团队 + 权限模型
- 计费 / 订阅
- Web 启动新 run 之外的高级运营面板
