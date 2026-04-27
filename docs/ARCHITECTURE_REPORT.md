# LarkMemory 架构梳理报告

更新时间：2026-04-27

## 0. 一句话结论

LarkMemory 当前已经打通了“飞书/OpenClaw 插件 -> 本地 Python 后端 -> 记忆写入/检索 -> 插件注入上下文”的主链路。系统的外壳已经成立，下一阶段的重点不是继续堆入口，而是把后端内部的 domain 检索、生命周期治理、评测闭环和数据边界打磨清楚。

这份报告按当前代码事实梳理，不把规划当成已完成能力。

## 1. 当前系统全景

```text
飞书机器人 / OpenClaw
        |
        v
plugin/index.ts
  - before_prompt_build: 写入用户消息 + 检索记忆 + 注入上下文
  - agent_end: 写入 Agent 回复
        |
        v
HTTP localhost
http://127.0.0.1:8765/api/v1
        |
        v
src/app/main.py  FastAPI 应用
        |
        v
src/api/*
  - /health
  - /ingest
  - /retrieve
  - /update
  - /proactive
  - /benchmark
        |
        v
src/core/service.py  MemoryService
        |
        +------------------+------------------+------------------+
        |                  |                  |                  |
        v                  v                  v                  v
src/storage/*      src/domains/*       src/retrieval/*      src/llm/*
SQLite/Chroma      project_decision    intent/rewrite/rank  optional LLM
```

当前架构是一个典型的“插件接入层 + 本地服务层 + 领域记忆引擎”的旁路架构。这个选择适合比赛和 MVP：入口可以快速跑通，内部可以逐步演化，不需要一开始就背上云服务、权限、多租户和真实飞书 API 的复杂度。

## 2. 源码目录职责

```text
LarkMemory/
├── plugin/                 # OpenClaw 插件，负责接入飞书/OpenClaw 和调用后端
├── src/
│   ├── app/                # FastAPI 应用启动、配置、依赖注入、日志
│   ├── api/                # HTTP API 边界
│   ├── core/               # 业务编排和记忆生命周期治理
│   ├── domains/            # 领域记忆能力，目前重点是 project_decision
│   ├── retrieval/          # 通用检索类型、意图分析、改写、融合、重排
│   ├── schemas/            # API 和内部共享数据契约
│   ├── storage/            # SQLite/Embedding 存储
│   ├── llm/                # LLM provider 和结构化调用封装
│   └── utils/              # ID、时间、文本、日志工具
├── tests/                  # 单元测试，覆盖 app/api/core/domain/retrieval/storage/utils
├── docs/                   # 设计和模块说明
└── memory-bank/            # 项目长期上下文、产品和架构记忆
```

## 3. 核心模块与职责

### 3.1 `plugin/`：OpenClaw 接入层

关键文件：

- `plugin/index.ts`
- `plugin/openclaw.plugin.json`
- `plugin/package.json`

当前职责：

- 注册 OpenClaw 插件入口。
- 监听两个关键 hook：
  - `before_prompt_build`
  - `agent_end`
- 从 event/ctx 中抽取用户消息、回复、用户 ID、项目 ID、线程 ID 等上下文。
- 调用后端：
  - `POST /api/v1/ingest`
  - `POST /api/v1/retrieve`
- 将检索结果拼成 `prependContext` 注入给 Agent。
- 后端不可用时只打日志，不让插件直接崩。

当前关键实现直觉：

```text
before_prompt_build
  -> extractText(event)
  -> ingestEvent(userMessage)
  -> retrieveMemories(userMessage)
  -> buildMemoryContext(results)
  -> return { prependSystemContext, prependContext }

agent_end
  -> extractReply(event)
  -> ingestEvent(reply)
```

模块边界：

- 插件层只做接入、请求、注入。
- 插件层不应该做长期记忆去重、覆盖、排序、抽取策略。
- 插件层是“手和嘴”，不是“大脑”。

### 3.2 `src/app/`：服务启动与运行时配置

关键文件：

- `main.py`
- `config.py`
- `dependencies.py`
- `logging.py`

当前职责：

- 创建 FastAPI app。
- 动态注册 API router。
- 从环境变量加载配置。
- 初始化 SQLite store、Embedding store、LLM client、MemoryService。
- 使用 `lru_cache` 缓存依赖对象。
- 配置结构化日志和请求日志中间件。

关键配置：

```text
LARKMEMORY_HOST              默认 127.0.0.1
LARKMEMORY_PORT              默认 8765
LARKMEMORY_SQLITE_PATH       默认 .larkmemory/larkmemory.db
LARKMEMORY_ENABLE_LLM        默认 false
LARKMEMORY_ENABLE_EMBEDDING  默认 false
LARKMEMORY_LOG_LEVEL         默认 INFO
```

依赖关系：

```text
app.main
  -> app.config
  -> app.logging
  -> app.dependencies
       -> storage.EventStore
       -> storage.MemoryCoreStore
       -> storage.EmbeddingStore?
       -> llm.LLMClient?
       -> core.MemoryService
```

### 3.3 `src/api/`：HTTP 边界层

关键文件：

- `health.py`
- `ingest.py`
- `retrieve.py`
- `update.py`
- `proactive.py`
- `benchmark.py`

当前职责：

- 接收 HTTP 请求。
- 用 Pydantic schema 做请求/响应校验。
- 将请求转换为内部 dataclass 或 retrieval query。
- 调用 `MemoryService`。
- 把内部结果转换成 API response。

当前接口：

```text
GET  /api/v1/health
POST /api/v1/ingest
POST /api/v1/retrieve
POST /api/v1/memories/search
POST /api/v1/update
POST /api/v1/memories/update
GET  /api/v1/proactive
POST /api/v1/benchmark/run
```

当前边界判断：

- API 层整体方向是对的：不直接写存储，不直接写复杂业务。
- `retrieve.py` 中还保留了 `_retrieve_fallback()`，但实际 `retrieve_memories()` 已经走 `MemoryService.retrieve()`。这类旧 fallback 后续应清理，避免团队误读。

### 3.4 `src/core/`：记忆业务编排层

关键文件：

- `service.py`
- `router.py`
- `admission_control.py`
- `dedup_merge.py`
- `supersede.py`
- `decay.py`
- `access_tracker.py`
- `scheduler.py`
- `memory_core.py`

当前职责：

- `MemoryService` 是后端统一业务入口。
- `DomainRouter` 根据事件/查询内容判断目标 domain。
- `AdmissionController` 判断事件或记忆是否值得进入长期记忆。
- `DedupMergeEngine` 做文本相似度去重和合并判断。
- `SupersedeManager` 做通用覆盖关系。
- `DecayPolicy` 计算 freshness 和过期状态。
- `AccessTracker` 记录近期访问和反馈，目前主要是内存队列。
- `Scheduler` 扫描 decay/review。

当前写入链路：

```text
MemoryService.ingest_event(event)
  -> EventStore.insert_event(event)
  -> DomainRouter.route_event(event)
  -> AdmissionController.evaluate_event(event)
  -> if primary_domain == "project_decision":
       ProjectDecisionExtractor.extract(event)
       ProjectDecisionVersionManager.detect_update(decision)
       MemoryService.add_memory(decision.to_memory_core())
       ProjectDecisionVersionManager.apply_supersede(...)
  -> IngestResult
```

当前检索链路：

```text
MemoryService.retrieve(query)
  -> IntentAnalyzer.analyze(query)
  -> QueryRewriter.rewrite(query, intent)
  -> MemoryCoreStore.list_active_memories(limit=max(top_k * 5, 20))
  -> memory_item_from_core(row)
  -> Reranker.rerank(candidates, rewritten)
  -> AccessTracker.record_access(...)
  -> RetrieveResult
```

重要现状：

- 写入侧已经接入 `project_decision` extractor 和 version manager。
- 检索侧还没有真正按 domain 调用 `ProjectDecisionRetriever`。
- 当前检索是 `memory_core_fallback`：加载所有 active memory，再统一 rerank。
- 这能跑通主链路，但不是最终架构。继续堆功能前，应优先把 domain retriever 接入 `MemoryService.retrieve()`。

### 3.5 `src/domains/project_decision/`：项目决策领域

关键文件：

- `models.py`
- `extractor.py`
- `retriever.py`
- `ranker.py`
- `versioning.py`

当前职责：

- 表达项目决策的领域模型。
- 从聊天/文档/事件文本中抽取决策候选。
- 将领域模型转换为统一 `MemoryCore`。
- 从 `MemoryCoreStore` 召回项目决策。
- 按 topic、project、stage、freshness、confidence、importance 排序。
- 检测同一项目/主题下的新旧决策覆盖关系。

领域模型核心：

```text
ProjectDecision
  - decision_id
  - project_id / workspace_id / team_id / thread_id
  - topic
  - decision / conclusion
  - stage
  - status
  - alternatives
  - reasons
  - participants
  - source_event_id / source_ref
  - decided_at / valid_from / valid_to
  - confidence / importance
  - overwrite_of / superseded_by
```

当前抽取方式：

- 规则优先。
- 有 LLM hook，但 `_extract_with_llm()` 目前返回空列表。
- 通过关键词识别：
  - 决定、确认、采用、选择、结论、截止日期
  - decision、confirmed、choose、deadline
- 支持抽取：
  - topic
  - decision text
  - deadline
  - alternatives
  - reasons
  - stage

关键提醒：

- `ProjectDecisionRetriever` 已经存在，但当前主 `MemoryService.retrieve()` 还没用它。
- `ProjectDecision` 目前通过 `MemoryCore.entities/tags/content_text` 保存领域信息，没有独立 `project_decision_store` 表。这个选择简单，但长期会让领域字段查询和结构化分析变别扭。

### 3.6 `src/retrieval/`：通用检索管线

关键文件：

- `_types.py`
- `intent_analyzer.py`
- `query_rewrite.py`
- `fusion.py`
- `rerank.py`
- `retrieval_trace.py`

当前职责：

- 定义 `RetrievalQuery`、`MemoryItem`、`DomainRecallResult`、`FusedCandidate`、`RankedMemory` 等检索中间模型。
- 分析查询意图，决定主查/辅查 domain。
- 对 query 做改写，补充 topic、scope、time、boost signals。
- 融合多 domain 召回结果。
- 最终重排。
- 记录检索 trace。

当前实际链路：

```text
IntentAnalyzer + QueryRewriter + Reranker 已接入 MemoryService.retrieve()
ResultFusion 和 domain retriever 尚未真正串入主检索链路
```

这意味着 retrieval 目录的能力部分已经可用，但还没有形成完整的：

```text
intent -> domain retrievers -> fusion -> rerank
```

当前更接近：

```text
intent -> rewrite -> load all active memory_core -> rerank
```

### 3.7 `src/storage/`：持久化层

关键文件：

- `base.py`
- `event_store.py`
- `memory_core_store.py`
- `embedding_store.py`

当前职责：

- `SQLiteStore` 封装 SQLite 基础操作。
- `EventStore` 保存标准化事件。
- `MemoryCoreStore` 保存统一记忆主表。
- `EmbeddingStore` 预留向量索引能力。

当前数据库事实：

```text
event_store
  - event_id
  - event_type
  - source_type
  - occurred_at
  - user_id / project_id / team_id / workspace_id / repo_id / thread_id
  - content_text
  - payload_json
  - raw_payload_json
  - tags_json

memory_core
  - memory_id
  - domain
  - memory_type
  - scope
  - source_type / source_ref / source_event_id
  - content_text / summary_text
  - entities_json / tags_json
  - importance / confidence / freshness_score
  - status
  - valid_from / valid_to
  - overwrite_of / superseded_by
  - policy / embedding / timestamps
```

当前没有独立的 project decision payload 表。项目决策结构被压缩进：

- `content_text`
- `summary_text`
- `entities_json`
- `tags_json`
- `overwrite_of`
- `superseded_by`

短期这符合 KISS，长期如果要做严肃评测和复杂筛选，需要补领域表或领域 payload 存储。

### 3.8 `src/schemas/`：协议层

关键文件：

- `event.py`
- `memory_core.py`
- `ingest.py`
- `retrieve.py`
- `update.py`
- `proactive.py`
- `benchmark.py`
- `llm.py`

当前职责：

- `event.py`、`memory_core.py` 使用 dataclass，服务内部使用。
- API request/response 使用 Pydantic `BaseModel`。
- schema 层是插件、API、core、storage 之间的共同语言。

重要契约：

```text
IngestRequest
  -> event_type
  -> source_type
  -> occurred_at
  -> context
  -> content_text
  -> payload/raw_payload/tags

RetrieveRequest
  -> query_text
  -> user_id/project_id/repo_id/workspace_id/team_id
  -> session_context
  -> top_k
  -> include_trace

MemoryHit
  -> memory_id/domain/memory_type/content_text
  -> summary_text/score/rank/scope/source_ref
  -> tags/entities/score_breakdown
```

### 3.9 `src/llm/`：模型调用封装

关键文件：

- `base.py`
- `client.py`
- `openai_provider.py`

当前职责：

- 封装 OpenAI-compatible provider。
- 支持结构化 JSON 调用。
- 通过 `LARKMEMORY_ENABLE_LLM` 控制是否启用。

当前状态：

- 默认关闭。
- IntentAnalyzer、QueryRewriter、ProjectDecisionExtractor 都有 LLM 接入位置。
- `ProjectDecisionExtractor._extract_with_llm()` 目前未实现实际抽取。

### 3.10 `src/utils/`：通用工具

关键文件：

- `ids.py`
- `time.py`
- `text.py`
- `jsonlog.py`

当前职责：

- 统一 ID 生成。
- ISO 时间处理、过期判断、天数计算。
- 文本清洗、截断、关键词判断。
- JSON 日志格式化。

这是健康的基础层，建议继续保持小而稳定。

## 4. 模块依赖关系

### 4.1 总体依赖方向

```text
plugin
  -> HTTP API

api
  -> schemas
  -> core.MemoryService

core
  -> schemas
  -> storage
  -> domains
  -> retrieval
  -> llm
  -> utils

domains
  -> schemas
  -> storage
  -> retrieval types
  -> utils

retrieval
  -> schemas
  -> llm
  -> utils

storage
  -> schemas
  -> utils

app
  -> api
  -> core
  -> storage
  -> llm
```

### 4.2 理想依赖方向

```text
Plugin
  -> API
    -> Service
      -> Domain modules
      -> Retrieval pipeline
      -> Lifecycle policies
      -> Stores
        -> SQLite / Chroma
```

原则：

- 上层可以依赖下层。
- 下层不要反向知道上层。
- API 不应该知道 SQLite 细节。
- 插件不应该知道后端内部 store/domain 细节。
- domain 内部可以依赖通用 retrieval 类型，但 retrieval 的主流程最好通过接口调用 domain retriever，避免互相纠缠。

## 5. 数据流和调用流程

### 5.1 写入流程

```text
飞书用户消息
  -> OpenClaw before_prompt_build
  -> plugin.extractText()
  -> plugin.collectContext()
  -> POST /api/v1/ingest
  -> api.ingest_event()
  -> NormalizedEvent
  -> MemoryService.ingest_event()
  -> EventStore.insert_event()
  -> DomainRouter.route_event()
  -> AdmissionController.evaluate_event()
  -> ProjectDecisionExtractor.extract()
  -> ProjectDecision.to_memory_core()
  -> ProjectDecisionVersionManager.detect_update()
  -> MemoryService.add_memory()
  -> DedupMergeEngine.find_duplicate()
  -> MemoryCoreStore.insert_memory_core()
  -> optional supersede
```

当前写入侧已经具有“事件入库 + 决策抽取 + MemoryCore 入库 + 新旧覆盖”的基本骨架。

### 5.2 检索流程

```text
飞书用户消息
  -> OpenClaw before_prompt_build
  -> POST /api/v1/retrieve
  -> api.retrieve_memories()
  -> RetrievalQuery
  -> MemoryService.retrieve()
  -> IntentAnalyzer.analyze()
  -> QueryRewriter.rewrite()
  -> MemoryCoreStore.list_active_memories()
  -> memory_item_from_core()
  -> Reranker.rerank()
  -> AccessTracker.record_access()
  -> RetrieveResponse
  -> plugin.buildMemoryContext()
  -> OpenClaw prependContext
```

当前检索能跑，但还不够“领域化”。现在的模式适合证明入口通了，不适合长期扩展。

下一步应该变成：

```text
RetrievalQuery
  -> IntentAnalyzer
  -> QueryRewriter
  -> DomainRouter.route_query
  -> ProjectDecisionRetriever.retrieve
  -> DomainRecallResult
  -> ResultFusion
  -> Reranker
```

### 5.3 更新流程

```text
POST /api/v1/update
  -> api.update_memory()
  -> MemoryService.update_memory()
  -> expire / forget / supersede / confidence / importance / feedback
  -> MemoryCoreStore or AccessTracker
```

当前 update 已支持基础操作，但 `correct` 还只是 accepted，未实现真正纠错写入。

### 5.4 主动服务和评测流程

```text
/proactive   -> MemoryService.proactive_suggestions() -> 当前返回空
/benchmark   -> 当前有 API shell，具体评测闭环仍需继续补
/maintenance -> MemoryService.run_maintenance() -> Scheduler decay/review
```

主动提醒、benchmark、复习计划目前仍属于骨架阶段。

## 6. 技术栈和关键实现

| 层级 | 技术/实现 | 当前状态 |
|---|---|---|
| 插件 | TypeScript, OpenClaw plugin SDK | 已接入 hook，并调用本地 API |
| API 服务 | FastAPI | 已有 app 和 router 注册 |
| 请求/响应 | Pydantic | API schema 已存在 |
| 内部模型 | dataclass | Event、MemoryCore、retrieval/domain 模型 |
| 存储 | SQLite | EventStore、MemoryCoreStore 已落地 |
| 向量索引 | Chroma 相关封装 | 可选，默认关闭 |
| LLM | OpenAI-compatible client | 可选，默认关闭，部分业务未实现 LLM 逻辑 |
| 检索 | 规则意图、query rewrite、rerank | 部分接入，domain retrieval/fusion 尚未接入主链路 |
| 测试 | pytest | 单测覆盖 app/api/core/domain/retrieval/storage/utils |
| 日志 | Python logging + request middleware | 已有结构化日志倾向 |

## 7. 当前架构中最重要的事实

### 7.1 已经完成的部分

- 插件到后端 API 的调用链路已经跑通。
- 后端 FastAPI 服务结构已经成型。
- `/ingest`、`/retrieve`、`/update` 等 API 已存在。
- `MemoryService` 已成为业务编排入口。
- 事件存储和 MemoryCore 存储已落地。
- `project_decision` domain 已有模型、抽取、检索、排序、版本管理。
- 写入链路已能抽取项目决策并写入 `memory_core`。
- 基础生命周期能力已有雏形：admission、dedup、supersede、decay、access tracking。

### 7.2 还没有真正完成的部分

- 主检索链路还没有接入 `ProjectDecisionRetriever`。
- `ResultFusion` 尚未进入 `MemoryService.retrieve()` 主流程。
- `ProjectDecision` 没有独立 payload store，结构化字段主要塞在 `MemoryCore` 文本、entities、tags 中。
- LLM 抽取 hook 存在，但 project decision 的 LLM fallback 未实现。
- access tracking 目前主要是内存态，没有持久化 access log store。
- proactive 当前返回空。
- benchmark 还没有成为可支撑比赛叙事的数据闭环。
- API 中存在旧 fallback/alias/占位逻辑，需要后续收敛。

## 8. 潜在耦合点和风险

### 8.1 `MemoryService` 正在变成“大管家”

现象：

- `MemoryService` 同时处理 ingest、retrieve、update、proactive、maintenance。
- 它直接实例化和调用 router、admission、dedup、supersede、extractor、version manager、retrieval 组件。

风险：

- 后续每加一个 domain，`MemoryService` 会继续膨胀。
- 查询链路和写入链路会混在一个类里。

建议：

- 短期不用大重构。
- 下一步只抽一个小接口：`DomainRetrieverRegistry` 或 `DomainRetrievalService`。
- 让 `MemoryService.retrieve()` 不直接关心具体 domain retriever。

### 8.2 检索链路没有真正领域化

现象：

- `ProjectDecisionRetriever` 已实现。
- `MemoryService.retrieve()` 仍然 `list_active_memories()` 加载所有 active 记忆，再统一 rerank。

风险：

- 数据一多会慢。
- 不同 domain 的召回逻辑混在一起，排序解释性差。
- `project_decision` 的 topic/project/stage 逻辑用不上。

建议优先级最高：

```text
MemoryService.retrieve()
  -> intent
  -> route domains
  -> call ProjectDecisionRetriever for project_decision
  -> wrap as DomainRecallResult
  -> ResultFusion
  -> Reranker
```

这是当前最值得做的架构修正。

### 8.3 domain payload 缺失

现象：

- 项目决策结构被编码进 `MemoryCore.content_text`、`entities`、`tags`。

风险：

- 查询靠字符串和 tag，长期不稳。
- benchmark 难精确统计字段级指标。
- 后续做 UI 卡片、版本链、决策 diff 会吃力。

建议：

- 短期保留当前 KISS 实现。
- 当 `project_decision` 检索接入后，再补 `ProjectDecisionStore` 或通用 `domain_payload_store`。
- 不要现在一次性为所有 domain 建表。

### 8.4 插件在 `before_prompt_build` 里先 ingest 再 retrieve

现象：

```text
before_prompt_build
  -> ingest 当前用户消息
  -> retrieve 当前用户消息相关记忆
```

风险：

- 当前用户消息可能被立刻抽成记忆，又被当前 query 检索到，产生“自回声”。
- 如果未来 extractor 更激进，可能污染上下文。

建议：

- 在 retrieve 时排除当前 `event_id` 或当前 hook 写入的 memory。
- 或调整为：

```text
retrieve old memories
-> build prompt
-> agent_end / after_prompt 再 ingest 新信息
```

权衡：

- 先 retrieve 后 ingest 更干净。
- 先 ingest 后 retrieve 更容易让同轮上下文完整，但需要排除自引用。

### 8.5 更新和纠错语义还不完整

现象：

- `expire`、`forget`、`supersede`、`confidence`、`importance` 可用。
- `correct` 只是 accepted，占位。

风险：

- 用户纠错是记忆系统最关键的数据质量入口。
- 如果纠错不落地，错误记忆会反复召回。

建议：

- 下一阶段给 `correct` 定义明确语义：
  - 修正文案？
  - 新 memory supersede 旧 memory？
  - 降低 confidence？
  - 标记需要 review？

### 8.6 依赖注入使用全局缓存

现象：

- `dependencies.py` 用 `lru_cache` 缓存 store/service/client。

风险：

- 本地单进程 MVP 没问题。
- 多环境测试、热重载、多 worker、不同配置切换时容易出状态问题。

建议：

- 现阶段保留。
- 测试里继续使用 `reset_dependency_cache()`。
- 到服务化/部署阶段再引入更明确的 application lifespan 和依赖容器。

### 8.7 无迁移系统

现象：

- store 通过 `CREATE TABLE IF NOT EXISTS` 建表。
- 没有 schema version 和 migration。

风险：

- 开发期字段变化后，旧本地 DB 可能静默缺字段。

建议：

- MVP 继续简单。
- 一旦加入 domain payload store，就补最小 migration：

```text
schema_version table
-> numbered migration functions
-> startup apply migrations
```

## 9. 推荐的下一步推进顺序

### Step 1：把主检索链路接入 `ProjectDecisionRetriever`

目标：

- 让已有 domain retriever 真正服务线上调用。

建议改动：

- `src/core/service.py`
- 可能新增 `src/core/retrieval_orchestrator.py`
- 更新 `tests/unit/core/test_service.py`
- 更新 `tests/unit/api/test_retrieve_api.py`

验收：

- query 命中 project decision 时，trace 不再只是 `memory_core_fallback`。
- 同 project 的决策优先返回。
- 不同 project 的同 topic 不串扰。
- `ProjectDecisionSearchResult.to_ranked_memory()` 的 decision card 能进入返回结果 extra 或 API 扩展字段。

### Step 2：解决插件“自回声”风险

目标：

- 当前消息不应该被刚写入又立刻作为历史记忆注入。

可选方案：

- 方案 A：`before_prompt_build` 先 retrieve，再 ingest。
- 方案 B：保留当前顺序，但 retrieve 请求带 `exclude_event_id` 或 `exclude_source_ref`。

建议：

- 优先方案 A，最简单，符合 KISS。

### Step 3：给项目决策补持久化 payload

目标：

- 从“把领域结构塞进 MemoryCore 文本”进化为“MemoryCore + ProjectDecision payload”。

建议：

- 新增 `src/storage/project_decision_store.py`。
- 或新增更通用的 `domain_payload_store`。

选择建议：

- 如果只服务比赛主线，先做 `ProjectDecisionStore`。
- 如果马上要扩多个 domain，做通用 payload store。

### Step 4：补 `correct` 语义

目标：

- 让用户反馈能改变记忆质量。

建议最小语义：

```text
correct(old_memory_id, corrected_text)
  -> create new MemoryCore
  -> mark old as superseded
  -> new.overwrite_of = old
```

这比原地改旧记忆更可追溯。

### Step 5：把 benchmark 做成可重复证据

目标：

- 用数据证明系统有价值。

最小场景：

- 抗干扰召回。
- 矛盾更新。
- 历史决策卡片节省查询步骤。

输出指标：

- hit@k
- target_rank
- active/superseded 状态正确率
- injected_memory_count
- simulated_saved_steps

## 10. 给团队的新开发约定

为了避免 vibe coding 变成屎山，建议后续每个 PR 或每次结对开发只问 5 个问题：

1. 这次改动属于哪个层？
   - plugin、api、core、domain、retrieval、storage、schema、llm、utils
2. 有没有跨层直接调用？
   - 比如 plugin 直接关心 storage 字段，这就是坏味道。
3. 有没有新增一个可测试闭环？
   - 没测试就不算完成。
4. 有没有把“规划能力”写成“当前事实”？
   - 文档必须区分已实现和待实现。
5. 有没有让 `MemoryService` 更胖？
   - 如果有，考虑是否需要抽一个小协作者。

## 11. 新人阅读顺序

建议新同学按这个顺序读：

```text
1. plugin/index.ts
   先看外部入口怎么触发。

2. src/app/main.py + src/app/dependencies.py
   看服务如何启动，依赖如何组装。

3. src/api/ingest.py + src/api/retrieve.py
   看 HTTP 协议和请求/响应。

4. src/core/service.py
   看主业务链路。

5. src/domains/project_decision/*
   看当前最重要的领域能力。

6. src/storage/event_store.py + src/storage/memory_core_store.py
   看数据实际怎么落库。

7. src/retrieval/*
   看检索意图、改写、融合、重排的通用能力。

8. tests/unit/core/test_service.py + tests/unit/api/*
   看系统行为的真实契约。
```

## 12. 架构状态总结

当前项目不是空架构，也不是完整记忆平台。它处在一个很典型的中间态：

```text
入口链路：已打通
服务骨架：已成立
项目决策 domain：已初步实现
检索主链路：仍偏 fallback
生命周期治理：有雏形，未完全闭环
评测证明：还需要补
```

最关键的下一刀不是加更多模块，而是把已经写好的 `project_decision` 领域能力接入主检索链路。这样系统会从“能被飞书机器人调用的记忆 demo”，推进到“有领域边界、有解释性、有可测价值的 Memory Engine”。
