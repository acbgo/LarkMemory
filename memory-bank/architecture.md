# Architecture

本文档只维护项目架构，不记录实施状态或开发批次。目标是让 agent 快速理解 LarkMemory 的系统边界、模块分层、核心数据流和各层职责。

## 1. 架构定位

LarkMemory 采用“OpenClaw TypeScript Plugin + 本地 Python Memory Engine”的旁路式架构。

```text
OpenClaw TypeScript Plugin
-> localhost Python Memory Engine
-> event normalization
-> memory extraction / storage / retrieval / update
-> ranked memories / proactive suggestions
-> OpenClaw context injection
```

设计原则：

- 插件层负责接入 OpenClaw、采集上下文、发起请求和注入记忆结果。
- Python Memory Engine 负责长期记忆的抽取、存储、检索、更新、遗忘和评估。
- 领域能力按 domain 拆分，跨领域公共能力放在 core、storage、retrieval、llm 等基础层。
- API 层是插件与 Python 引擎之间的稳定边界，内部实现可以演进，但请求/响应协议应保持清晰。

## 2. 总体分层

```text
LarkMemory/
├── plugin/                         # OpenClaw 插件接入层
│   ├── index.ts                    # 插件入口，采集上下文并调用本地服务
│   ├── package.json                # 插件工程配置
│   └── openclaw.plugin.json        # OpenClaw 插件元信息
│
├── app/                            # Python Memory Engine 服务入口
│   ├── main.py                     # FastAPI 应用启动与 router 注册
│   ├── config.py                   # 端口、路径、模型参数、运行开关
│   ├── dependencies.py             # service、store、LLM client 等依赖注入
│   └── logging.py                  # 结构化日志与请求链路日志
│
├── api/                            # HTTP API 边界层
│   ├── ingest.py                   # 事件写入入口
│   ├── retrieve.py                 # 记忆检索入口
│   ├── update.py                   # 记忆纠正、覆盖、失效与反馈
│   ├── proactive.py                # 主动提醒、建议和复习结果
│   ├── benchmark.py                # 评测任务入口
│   └── health.py                   # 健康检查
│
├── core/                           # 业务编排与记忆生命周期治理
│   ├── service.py                  # 统一业务入口
│   ├── domain_handler.py           # domain handler 协议与运行时接口
│   ├── router.py                   # 事件和查询的领域路由
│   ├── memory_core.py              # 统一记忆对象与状态流转
│   ├── admission_control.py        # 长期记忆准入判断
│   ├── dedup_merge.py              # 重复识别与合并
│   ├── supersede.py                # 新旧版本覆盖关系
│   ├── decay.py                    # 衰减、归档和遗忘策略
│   ├── access_tracker.py           # 命中、采纳和反馈记录
│   └── scheduler.py                # 复习、提醒和过期扫描调度
│
├── domains/                        # 领域记忆能力
│   ├── cli_workflow/               # CLI 命令、排障、部署和工作流
│   │   ├── models.py
│   │   ├── extractor.py
│   │   ├── retriever.py
│   │   ├── ranker.py
│   │   └── workflow_miner.py
│   ├── project_decision/           # 项目决策、理由、备选方案和取舍
│   │   ├── models.py
│   │   ├── extractor.py
│   │   ├── handler.py
│   │   ├── retriever.py
│   │   ├── ranker.py
│   │   └── versioning.py
│   ├── personal_preference/        # 用户偏好、习惯和默认配置
│   │   ├── models.py
│   │   ├── extractor.py
│   │   ├── retriever.py
│   │   ├── ranker.py
│   │   └── pattern_miner.py
│   └── team_retention/             # 团队关键事实、风险、提醒和复习
│       ├── models.py
│       ├── extractor.py
│       ├── handler.py
│       ├── retriever.py
│       ├── ranker.py
│       ├── review_planner.py
│       └── versioning.py
│
├── retrieval/                      # 跨领域检索管线
│   ├── _types.py                   # 检索链路共享数据模型
│   ├── intent_analyzer.py          # 查询意图和目标领域分析
│   ├── query_rewrite.py            # topic、时间、scope、boost 信号补全
│   ├── fusion.py                   # 多领域召回融合
│   ├── rerank.py                   # 统一重排
│   └── retrieval_trace.py          # 检索链路追踪
│
├── storage/                        # 持久化与索引层
│   ├── event_store.py              # 原始或标准化事件存储
│   ├── memory_core_store.py        # 统一记忆主数据存储
│   ├── cli_workflow_store.py       # CLI 领域 memory 持久化
│   ├── project_decision_store.py   # 决策领域 memory 持久化
│   ├── personal_preference_store.py # 偏好领域 memory 持久化
│   ├── team_retention_store.py     # 团队保留领域 memory 持久化
│   ├── embedding_store.py          # 向量索引和语义检索
│   ├── access_log_store.py         # 命中、采纳和反馈日志
│   └── review_schedule_store.py    # 复习计划和提醒时间
│
├── llm/                            # LLM provider 与结构化调用封装
│   ├── base.py                     # provider 抽象
│   ├── client.py                   # 统一 LLM client
│   ├── openai_provider.py          # OpenAI provider
│   ├── prompts.py                  # 通用提示词模板
│   ├── extraction_prompts.py       # 抽取任务提示词
│   └── decision_prompts.py         # 决策任务提示词
│
├── schemas/                        # API 与内部模块共享协议
│   ├── event.py                    # 事件模型
│   ├── memory_core.py              # 统一记忆模型
│   ├── ingest.py                   # 写入请求和响应
│   ├── retrieve.py                 # 检索请求和响应
│   ├── update.py                   # 更新请求和响应
│   ├── proactive.py                # 主动提醒请求和响应
│   ├── benchmark.py                # 评测任务和结果
│   └── llm.py                      # LLM 结构化结果模型
│
├── jobs/                           # 后台任务
│   ├── review_scan.py              # 复习和提醒扫描
│   ├── decay_compaction.py         # 衰减、归档和压缩
│   └── benchmark_runner.py         # 评测执行
│
└── utils/                          # 通用工具
    ├── ids.py                      # ID 生成与解析
    ├── time.py                     # 时间处理
    ├── text.py                     # 文本清洗和规范化
    └── jsonlog.py                  # JSON 日志辅助
```

## 3. 插件层 `plugin/`

插件层运行在 OpenClaw 侧，是 LarkMemory 接入宿主环境的边界。

职责：

- 监听 OpenClaw 生命周期、会话上下文、工具调用和用户反馈。
- 将命令、对话、文档、会议、用户操作等上下文整理为请求，发送给本地 Python Memory Engine。
- 在用户提问、工具执行或 agent 决策前请求相关记忆。
- 将检索结果注入 prompt、tool context，或展示为记忆卡片。
- 探测和拉起本地服务，保证插件侧调用 localhost API。

插件层不负责：

- 长期记忆存储。
- 记忆去重、覆盖、遗忘。
- 跨领域排序和语义重排。
- 领域抽取策略。

## 4. 服务与 API 层 `app/`、`api/`

服务层负责启动 Python Memory Engine，并提供稳定 HTTP API。

### `app/`

职责：

- 创建 FastAPI 应用。
- 注册 API router。
- 初始化配置、日志、依赖对象和后台任务。
- 管理服务生命周期。

典型文件：

- `main.py`：服务入口。
- `config.py`：端口、路径、模型参数、运行开关。
- `dependencies.py`：统一提供 service、store、LLM client 等依赖。
- `logging.py`：结构化日志和请求链路日志。

### `api/`

职责：

- 接收插件或外部工具请求。
- 做请求校验和响应序列化。
- 调用 core service，不直接实现复杂业务逻辑。
- 保持 API 协议稳定。

核心接口：

- `POST /ingest`：接收标准化事件或原始事件，触发记忆写入流程。
- `POST /retrieve`：根据查询和上下文返回相关记忆。
- `POST /update`：处理记忆纠正、覆盖、失效和反馈。
- `GET /proactive`：返回提醒、建议、复习等主动结果。
- `POST /benchmark/run`：运行评测任务。
- `GET /health`：服务和依赖健康检查。

## 5. 业务编排层 `core/`

`core/` 是长期记忆系统的业务中枢，负责把 API、domain、storage、retrieval 连接成完整流程。

职责：

- 将事件或查询路由到合适的领域模块。
- 管理统一记忆对象和生命周期状态。
- 判断候选信息是否值得进入长期记忆。
- 处理重复、合并、覆盖和版本链。
- 记录访问、命中、采纳和用户反馈。
- 调度复习、提醒、过期扫描和衰减任务。

典型模块：

- `service.py`：统一业务入口，API 层优先调用它。
- `domain_handler.py`：定义 `MemoryDomainHandler` 协议、写入运行时和领域更新结果，core 通过该协议调用 domain。
- `router.py`：根据事件类型、上下文或查询意图选择 domain。
- `memory_core.py`：统一记忆对象和状态流转规则。
- `admission_control.py`：决定候选信息是否进入长期记忆。
- `dedup_merge.py`：识别重复内容并合并相近记忆。
- `supersede.py`：维护新旧记忆覆盖和版本关系。
- `decay.py`：记忆衰减、归档和遗忘策略。
- `access_tracker.py`：记录命中、采纳和反馈。
- `scheduler.py`：调度后台复习、提醒和过期扫描。

core 与 domain 的边界：

- `MemoryService` 只依赖 `MemoryDomainHandler` 协议，不直接 import 具体 domain 类。
- `app/dependencies.py` 负责注册 `ProjectDecisionDomainHandler`、`TeamRetentionDomainHandler` 等具体 handler。
- domain handler 封装本领域的 extractor、retriever、versioning 和领域 store 协作，对 core 暴露统一的 ingest、retrieve、update、proactive 接口。
- 新增 domain 时优先新增 domain package 和 handler，并在依赖注入处注册；不应继续扩展 `MemoryService` 的硬编码 if/elif。

## 6. 领域层 `domains/`

领域层按记忆类型拆分，每个 domain 负责本领域的结构化模型、抽取、召回和领域内排序。

```text
domains/
├── cli_workflow/
├── project_decision/
├── personal_preference/
└── team_retention/
```

### 通用领域结构

每个 domain 通常包含：

- `models.py`：领域结构化数据模型。
- `extractor.py`：从事件、文本或上下文中抽取领域记忆。
- `handler.py`：对 core 暴露统一领域接口，编排本领域抽取、召回、版本和领域 store。
- `retriever.py`：根据查询、scope、topic、time 等条件召回领域记忆。
- `ranker.py`：领域内排序。
- 领域专属辅助模块：如 workflow mining、pattern mining、review planning、versioning。

### `cli_workflow`

管理 CLI 工作流记忆。

关注内容：

- 高频命令。
- 构建、部署、排障流程。
- 参数偏好。
- shell、git、docker、kubectl、npm、pip 等操作经验。
- 多步命令序列形成的稳定 workflow。

### `project_decision`

管理项目决策记忆。

关注内容：

- 技术选型。
- 架构方案。
- 决策理由。
- 备选方案和 trade-off。
- 阶段性结论和后续覆盖关系。

### `personal_preference`

管理个人偏好记忆。

关注内容：

- 用户习惯。
- 默认工具或参数偏好。
- 编码风格。
- 交互偏好。
- 重复行为中挖掘出的稳定模式。

### `team_retention`

管理团队保留记忆。

关注内容：

- 团队关键事实。
- 合规和风险事项。
- 截止日期和提醒。
- 复习计划。
- 需要长期保留但容易被遗忘的信息。

当前模型边界：

- `TeamRetentionMemory`、`TeamReviewSchedule`、`RetentionFactType`、`RetentionRiskLevel`、`RetentionReviewPolicy` 定义在 `domains/team_retention/models.py`。
- `storage/team_retention_store.py` 只负责 `TeamRetentionMemory` 与 SQLite 表之间的写入、读取、查询、复习计划更新和行转换。
- `domains/team_retention/handler.py` 负责把 extractor 产出的 `TeamRetentionMemory` 写入 `MemoryCoreStore` 和 `TeamRetentionStore`，并处理重复强化、版本覆盖、复习提醒和领域更新动作。

## 7. 检索层 `retrieval/`

检索层负责把多个领域召回结果转成统一、可排序、可解释的记忆结果。

核心流程：

```text
RetrievalQuery
-> IntentAnalyzer
-> QueryRewriter
-> domain retrievers
-> ResultFusion
-> Reranker
-> RankedMemory[]
```

模块职责：

- `_types.py`：检索链路内部共享数据模型。
- `intent_analyzer.py`：分析查询意图，决定主查和辅查领域。
- `query_rewrite.py`：补全 topic、time window、scope filter、boost signals。
- `fusion.py`：融合多领域召回结果，重复召回同一记忆时累加证据。
- `rerank.py`：基于 fusion、importance、confidence、freshness、topic overlap、scope match 等因子统一重排，可选 LLM listwise rerank。
- `retrieval_trace.py`：记录检索链路步骤、输入输出摘要、耗时和嵌套结构。

检索层边界：

- 不直接访问插件。
- 不负责 HTTP 请求/响应。
- 不负责领域内抽取。
- 不负责存储写入生命周期。
- domain retriever 输出应适配为 `DomainRecallResult`，跨领域逻辑交给 fusion 和 rerank。

## 8. 存储层 `storage/`

存储层负责数据持久化和检索索引，不承载复杂业务决策。

主要存储对象：

- `event_store`：原始或标准化事件，用于回放、调试和评测。
- `memory_core_store`：统一记忆主表，保存跨领域公共字段。
- domain memory store：持久化各领域 `models.py` 中定义的结构化 memory 字段。
- `embedding_store`：保存向量索引和语义检索信息。
- `access_log_store`：保存检索命中、采纳、反馈等访问记录。
- `review_schedule_store`：保存复习计划和下一次提醒时间。

存储层原则：

- 只处理持久化、读取、索引和基础查询。
- 复杂生命周期决策应放在 `core/`。
- 领域特定结构应通过 domain memory store 扩展，不污染统一 memory core。
- 领域 dataclass/model 定义放在 `domains/*/models.py`；storage 复用这些模型完成数据库交互，不在 store 内重新定义业务模型。
- API、core、retrieval 应通过明确接口访问存储，而不是直接依赖文件或数据库细节。

## 9. LLM 层 `llm/`

LLM 层封装模型供应商和结构化调用能力。

职责：

- 统一 provider 接口。
- 支持 JSON/schema 约束输出。
- 隔离 OpenAI 或其他模型供应商细节。
- 为抽取、意图分析、查询改写、语义重排等任务提供能力。
- 允许业务层在 LLM 不可用时降级到规则策略。

典型模块：

- `base.py`：provider 抽象。
- `openai_provider.py`：OpenAI provider。
- `client.py`：统一业务 client。
- prompt 相关模块：集中管理抽取、决策、检索等任务的提示词。

## 10. Schema 层 `schemas/`

Schema 层定义系统内外的数据协议，是 API、core、storage、retrieval 之间的共同语言。

主要模型类别：

- event schema：标准化事件输入输出。
- memory core schema：统一记忆对象。
- ingest schema：写入接口请求和响应。
- retrieve schema：检索接口请求和响应。
- update schema：更新接口请求和响应。
- proactive schema：主动提醒和建议。
- benchmark schema：评测任务和结果。
- llm schema：结构化 LLM 调用结果。

设计原则：

- schema 应表达业务语义，而不是数据库实现细节。
- API 层和 storage 层都应复用 schema，减少重复模型。
- 跨模块传递的数据优先使用结构化模型，而不是裸 dict。

## 11. 后台任务层 `jobs/`

后台任务层处理不适合阻塞 API 请求的长期任务。

典型任务：

- `review_scan.py`：扫描需要复习、提醒或主动推送的记忆。
- `decay_compaction.py`：处理低活跃记忆的衰减、归档和压缩。
- `benchmark_runner.py`：执行评测任务并保存结果。

后台任务不直接暴露给插件，应通过 API 或 core service 提供触发和查询能力。

## 12. 核心数据流

### 写入流

```text
raw event
-> NormalizedEvent
-> domain router
-> domain extractor
-> MemoryCore + domain memory
-> admission control
-> dedup / merge / supersede
-> storage write
```

说明：

- raw event 可以来自 OpenClaw 会话、CLI、飞书聊天、飞书文档、会议纪要等。
- NormalizedEvent 保留 source、scope、project、team、workspace、occurred_at、payload 等上下文。
- domain extractor 将事件转为候选记忆。
- admission control 决定是否写入长期记忆。
- dedup / merge / supersede 负责生命周期治理。
- storage 保存 memory core、domain memory 和索引。

### 检索流

```text
query + context
-> RetrievalQuery
-> intent analysis
-> query rewrite
-> target domain retrieval
-> domain rerank
-> cross-domain fusion
-> unified rerank
-> top memories
-> context injection / memory card
```

说明：

- IntentAnalyzer 决定主查和辅查领域。
- QueryRewriter 补全 topic、时间窗口、scope filter 和 boost signals。
- domain retriever 只负责领域内召回。
- ResultFusion 负责跨领域融合。
- Reranker 负责最终统一重排。
- 插件层负责把结果注入 OpenClaw 上下文。

### 更新与遗忘流

```text
user feedback / correction / conflict / expiry signal
-> update API
-> core lifecycle policy
-> merge / supersede / expire / forget
-> storage update
-> access log / review schedule update
```

说明：

- 低置信度信息可进入 candidate 状态。
- 重复信息应合并，而不是无限插入。
- 冲突信息通过 supersede 建立新旧版本关系。
- 检索默认优先返回 active 记忆。
- 不同 domain 可以使用不同 decay 和 forgetting 策略。

## 13. 关键数据概念

### Memory Core

所有记忆共享的主数据，负责跨领域通用字段。

典型字段：

- `memory_id`
- `domain`
- `scope`
- `source`
- `content_text`
- `summary_text`
- `importance`
- `confidence`
- `status`
- `valid_from`
- `valid_to`
- `overwrite_of`
- `superseded_by`
- `created_at`
- `updated_at`

### Domain Memory

领域专属结构化数据。它与 Memory Core 通过 `memory_id` 关联。

示例：

- CLI 领域保存 command、args、exit_code、cwd、repo、workflow pattern。
- 决策领域保存 decision、rationale、alternatives、tradeoffs、stage。
- 偏好领域保存 preference、context、confidence source、pattern。
- 团队保留领域保存 risk level、review cadence、owner、deadline。

### Retrieval Result

检索输出应包含：

- 记忆内容。
- 来源 domain。
- relevance score。
- rank。
- 可解释的 score breakdown。
- 可选 trace/debug 信息。

## 14. 模块边界约束

- 插件层只做接入和注入，不做长期记忆治理。
- API 层只做协议边界，不直接写复杂业务逻辑。
- core 层负责业务编排和生命周期策略。
- domain 层负责领域内抽取、召回、排序。
- retrieval 层负责跨领域检索管线。
- storage 层负责持久化和索引，不做 admission、dedup、supersede 决策。
- llm 层负责模型调用封装，不绑定具体业务流程。
- schemas 层定义协议，不依赖业务实现。

## 15. Agent 接手时的阅读顺序

为了快速理解架构，建议按以下顺序阅读：

1. `memory-bank/architecture.md`：系统分层和边界。
2. `memory-bank/prd.md`：产品目标和用户价值。
3. `docs/DEVELOPMENT PLAN.md`：模块规划和文件职责。
4. `docs/Memory Structure and Storage.md`：记忆结构和存储设计。
5. `src/retrieval/`：检索管线实现。
6. `src/storage/`：存储接口和实现。
7. `src/schemas/`：共享数据协议。
