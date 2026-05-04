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
├── sources/                        # 外部消息源接入层
│   ├── _shared/                    # 多信息源共享基础设施
│   │   └── chunker.py              # 通用文本切分工具（Markdown 标题切分 / 妙记章节切分）
│   │
│   ├── feishu/                     # 飞书消息源、卡片推送和回调适配
│   │   ├── client/                 # 飞书 SDK 连接与监听
│   │   │   ├── config.py           # 飞书企业自建应用凭证和运行配置
│   │   │   ├── sdk.py              # lark-oapi OpenAPI/WebSocket client 工厂
│   │   │   └── listener.py         # 飞书 WebSocket 事件监听入口（多事件类型注册）
│   │   ├── events/                 # 飞书事件模型、标准化和分发
│   │   │   ├── models.py           # 飞书 IM 消息、卡片动作和原始事件模型
│   │   │   ├── normalizer.py       # 飞书 IM 消息转 NormalizedEvent
│   │   │   ├── dispatcher.py       # 标准化事件分发到 MemoryService（通用）
│   │   │   ├── calendar_models.py  # 飞书日历事件模型
│   │   │   ├── calendar_normalizer.py  # 日历事件→NormalizedEvent (1:1)
│   │   │   ├── task_models.py      # 飞书任务事件模型
│   │   │   ├── task_normalizer.py  # 任务事件→NormalizedEvent (1:1)
│   │   │   ├── meeting_models.py   # 飞书会议/妙记事件模型
│   │   │   ├── meeting_normalizer.py   # 会议总结/章节/待办→NormalizedEvent
│   │   │   ├── meeting_processor.py    # 妙记多步骤编排(等AI→拉取产物→切chunk)
│   │   │   ├── doc_models.py       # 飞书文档事件模型
│   │   │   ├── doc_normalizer.py   # 文档章节→NormalizedEvent
│   │   │   └── doc_processor.py    # 文档变更处理(拉取→diff→切chunk)
│   │   ├── scanner/                # 定时轮询扫描（兜底非 WebSocket 场景）
│   │   │   └── meeting_scanner.py  # 妙记增量扫描
│   │   └── proactive/              # 飞书主动服务输出与反馈
│   │       ├── cards.py            # 主动提醒 suggestion 转飞书互动卡片
│   │       ├── notifier.py         # 调用飞书 API 发送文本和互动卡片
│   │       └── callbacks.py        # 卡片按钮动作转 MemoryService 更新
│   └── cli/                        # CLI 终端客户端工具（lark-memory 命令）
│       ├── main.py                 # CLI 入口，5 个子命令路由
│       ├── hook.py                 # Shell hook 安装/卸载/检测（标记块、可逆幂等）
│       ├── ingest.py               # 命令捕获 → 事件构造 → POST /api/v1/ingest
│       ├── retrieve.py             # suggest 查询 / complete 补全 → POST /api/v1/retrieve
│       ├── completion.py           # 动态生成 bash/zsh completion script
│       └── _client.py              # 公共 HTTP 客户端（get_api_base / post_ingest / post_retrieve）
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
│   ├── domain_classifier.py        # 统一四域分类器（LLM atext()+硬规则+关键词降级）
│   ├── router.py                   # 事件路由（委托 DomainClassifier）
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
│   │   ├── models.py               # CLIWorkflowMemory + ParameterBinding + MemoryCore 双向转换
│   │   ├── extractor.py            # Shell/OpenClaw 事件 → 命令模板 + 参数绑定提取
│   │   ├── handler.py              # MemoryDomainHandler 协议实现，编排完整写入链路
│   │   ├── retriever.py            # 按 user/project/command 过滤 + 多维度打分检索
│   │   └── versioning.py           # Shell 强化 / OpenClaw 覆盖 / 跨源优先级
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
│   │   ├── handler.py
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
│   ├── intent_analyzer.py          # 查询意图分析（委托 DomainClassifier）
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
│   ├── review_schedule_store.py    # 复习计划和提醒时间
│   └── source_state_store.py       # Source 层外部资源处理状态（书签/游标/指纹）
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

## 4. Source Adapter 层 `sources/`

Source Adapter 层负责监听外部平台事件、调用外部平台 API，并把平台原始事件转换为项目统一协议；它不承载长期记忆业务判断。

### `sources/feishu/`

飞书接入按三层拆分：`client/` 负责平台连接，`events/` 负责事件标准化与分发，`proactive/` 负责主动卡片推送和按钮反馈。

典型链路：

```text
Feishu WebSocket / OpenAPI
-> sources/feishu/client
-> sources/feishu/events
-> NormalizedEvent
-> MemoryService
-> domain handlers
```

主动服务链路：

```text
MemoryService.proactive_suggestions()
-> sources/feishu/proactive/cards.py
-> sources/feishu/proactive/notifier.py
-> Feishu interactive card
-> card.action.trigger
-> sources/feishu/proactive/callbacks.py
-> MemoryService.update_memory()
```

文件职责：

- `client/config.py`：读取 `LARKMEMORY_FEISHU_*` 配置；`APP_ID` 和 `APP_SECRET` 是飞书企业自建应用凭证，不是用户登录态。
- `client/sdk.py`：懒加载 `lark-oapi`，创建飞书 OpenAPI client 和 WebSocket client。
- `client/listener.py`：注册飞书消息事件和卡片回调，收到事件后委托 events/proactive 层处理。
- `events/models.py`：定义飞书消息、卡片动作和原始事件 envelope 的内部模型。
- `events/normalizer.py`：将飞书 IM 消息转成 `NormalizedEvent(event_type="chat_message", source_type="feishu_chat")`。
- `events/dispatcher.py`：调用 `MemoryService.ingest_event()`，并容忍飞书重试导致的重复事件。
- `proactive/cards.py`：将 `review_reminder` suggestion 渲染为飞书 interactive card JSON。
- `proactive/notifier.py`：封装 `im.v1.message.create`，发送飞书文本和互动卡片。
- `proactive/callbacks.py`：解析卡片按钮，将 `reviewed`、`snooze`、`expire`、`forget` 映射到 `MemoryService.update_memory()`。

当前约定：飞书 `chat_id` 暂时映射到 `EventContext.team_id`，并写入 `payload["chat_id"]`，用于方向 D 的群级团队记忆和后续主动推送。

边界约束：

- `core/`、`domains/`、`storage/` 不依赖 `sources/feishu/`。
- 飞书 listener 不做长期记忆判断，不直接调用 domain extractor。
- 飞书卡片 JSON 构造不调用飞书 API；发送逻辑只放在 notifier。
- 当前本地实现可以进程内调用 `MemoryService`；后续可替换为 HTTP 调用 `/api/v1/ingest` 和 `/api/v1/update`。

### `sources/_shared/` — 多信息源共享工具

**`chunker.py`** — 纯文本切分工具，无 DB 依赖，无外部服务依赖：

- `split_by_headings(markdown_text)` → `list[ChunkResult]`：按 Markdown H1/H2 标题切分，用于文档分段。
- `split_by_chapters(verbatim_text, chapter_list)` → `list[ChunkResult]`：按妙记 AI 章节时间戳切分逐字稿，用于会议内容分段。
- `ChunkResult` 包含 `chunk_id, heading/heading_level, content, index`，可直接映射到 `NormalizedEvent.title` 和 `content_text`。

### `storage/source_state_store.py` — Source 层外部资源处理状态

属于 storage 层（复用 `SQLiteStore` 基类），对 source adapter 暴露稳定的读写接口。

- 独立 DB 文件 `.larkmemory/source_state.db`，与后端记忆引擎 DB 物理隔离。
- 表 `source_processed(source_type, external_id, status, last_hash, cursor_value, metadata_json, processed_at, error_count)`。
- 只做"书签/游标/指纹"，不存储业务数据（事件、记忆）。
- 使用场景：
  - 妙记 scanner：判断 meeting 是否已处理、AI 产物是否就绪。
  - 文档 processor：对比内容 hash 判断是否有实质变更，避免重复抽取无变化的文档。
- source adapter 通过依赖注入获取 `SourceStateStore` 实例，不直接持有 DB 连接。

### 多信息源扩展模式

新增信息源按复杂度分为两类，采用不同的处理模式：

**┌─────────────────────────────────────────────────────────────────┐**
**│ 类型 A：事件驱动 + 1:1 映射（日历、任务）                          │**
**│                                                                  │**
**│ WS 事件 → xxx_normalizer.py  → 1 条 NormalizedEvent              │**
**│                (1:1 映射)     → dispatcher.dispatch()            │**
**│                                                                │**
**│ 不需要 source_state_store，不需要 chunker。                       │**
**└─────────────────────────────────────────────────────────────────┘**

**┌─────────────────────────────────────────────────────────────────┐**
**│ 类型 B：事件触发 + 多步骤 + 1:N 切分（妙记、文档）                  │**
**│                                                                  │**
**│ WS 事件 → xxx_processor.py → 拉取外部数据 → chunker 切分          │**
**│                              → 每条 chunk → xxx_normalizer.py    │**
**│                              → N 条 NormalizedEvent               │**
**│                              → dispatcher.dispatch_all()         │**
**│                              → source_state_store 记录状态        │**
**│                                                                  │**
**│ 需要 source_state_store（幂等+书签）+ chunker（切分）+ processor。  │**
**│ 轮询兜底由 scanner/ 提供。                                        │**
**└─────────────────────────────────────────────────────────────────┘**

各模块职责边界：

| 模块 | 职责 | 适用于 |
|------|------|--------|
| `xxx_normalizer.py` | 1 条外部数据→1 条 NormalizedEvent 的纯映射 | 所有信息源 |
| `xxx_processor.py` | 多步骤编排：拉取外部API→等AI产物→切分→批量写入→标记状态 | 妙记、文档 |
| `chunker.py` | 纯文本切分：按标题/章节将长文本切为独立片段 | 妙记逐字稿、文档正文 |
| `scanner/*.py` | 定时轮询：按间隔扫描新数据源，兜底非 WebSocket 场景 | 妙记非会议上传 |
| `source_state_store.py` | 记录"哪个外部资源已处理到什么程度" | processor、scanner |

### 新增信息源的数据流

**飞书日历（事件驱动 + 1:1 映射）：**

```text
Feishu WebSocket calendar.event.changed_v4
→ listener.on_calendar_event()
→ calendar_normalizer.calendar_event_to_normalized_event()
    event_type="calendar_event", source_type="feishu_calendar"
    content_text=标题+描述, payload={start_time, end_time, attendees, ...}
→ dispatcher.dispatch_normalized_event()
→ MemoryService.ingest_event()
```

**飞书任务（事件驱动 + 1:1 映射）：**

```text
Feishu WebSocket task.updated_v2
→ listener.on_task_event()
→ task_normalizer.task_event_to_normalized_event()
    event_type="task_created/updated/completed", source_type="feishu_task"
    content_text=任务名+描述, payload={status, due_time, assignees, tasklist, ...}
→ dispatcher.dispatch_normalized_event()
→ MemoryService.ingest_event()
```

**飞书妙记（事件触发 + 多步骤 + 按章节切 chunk）：**

```text
Feishu WebSocket vc.meeting.ended_v1
→ listener.on_meeting_ended()
→ meeting_processor.process_meeting_ended(meeting_id)
    ├─ source_state_store: 幂等检查
    ├─ vc +recording → minute_token
    ├─ 延迟 5min 等待 AI 产物生成
    ├─ vc +notes → summary + todos + chapters + verbatim
    ├─ chunker.split_by_chapter(verbatim, chapters) → N 条章节 chunk
    ├─ normalizer: 每个 chunk → NormalizedEvent(event_type="meeting_chapter")
    ├─ normalizer: summary → NormalizedEvent(event_type="meeting_summary")
    ├─ normalizer: 每条 todo → NormalizedEvent(event_type="meeting_todo")
    ├─ dispatcher.dispatch_all([summary, *chapters, *todos])
    └─ source_state_store.mark_complete()
```

**飞书文档（事件触发 + diff + 按标题切 chunk）：**

```text
Feishu WebSocket doc.updated_v1
→ listener.on_doc_changed()
→ doc_processor.process_doc(doc_token)
    ├─ docs +fetch → markdown 全文
    ├─ source_state_store: 对比 last_hash → 无变更跳过
    ├─ chunker.split_by_headings(markdown) → 按 H1/H2 切分
    ├─ 仅变更章节 → normalizer.doc_section_to_event()
    │   event_type="doc_section", source_type="feishu_doc"
    ├─ dispatcher.dispatch_all(chapter_events)
    └─ source_state_store: 更新 hash + processed_at
```

## 5. 服务与 API 层 `app/`、`api/`

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

## 6. 业务编排层 `core/`

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

## 7. 领域层 `domains/`

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

管理 CLI 工作流记忆。采用双通道设计：CLI shell 被动监听（隐式记忆）+ OpenClaw 显式教学（显式记忆）。

关注内容：

- 高频命令和参数偏好。
- 构建、部署、排障流程。
- shell、git、docker、kubectl、npm、pip 等操作经验。
- 跨项目的命令行参数差异（"项目 A 用 --env prod，项目 B 用 --env staging"）。

记忆模型：

- `CLIWorkflowMemory`：命令模板 + 参数绑定 + 执行次数 / 成功率 / 新鲜度。
- user_id / project_id / command_name 编码进 MemoryCore entities，参数绑定编码进 tags（`param:env=prod`），零侵入通用表结构。

更新策略：

- Shell 同命令重复执行 → reinforce（execution_count++、合并参数频率）。
- OpenClaw 显式教学 → 覆盖 shell 统计（supersede），用户明确意图优先于机器统计。
- Shell 不覆盖已有的 OpenClaw 记忆。

输出通道：

- CLI Tab 补全（`lark-memory complete`）→ 参数名 + 值候选，按频率排序。
- CLI 主动查询（`lark-memory suggest`）→ 命令模板 + 参数绑定 + 执行统计。
- OpenClaw 主动推荐（`before_prompt_build`）→ 注入 Agent 上下文。

当前不做：工作流序列挖掘（前序/后续命令关联），后续迭代。

### `project_decision`

管理项目决策记忆。

关注内容：

- 技术选型。
- 架构方案。
- 决策理由。
- 备选方案和 trade-off。
- 阶段性结论和后续覆盖关系。

### `personal_preference`

管理个人偏好记忆（🔜 待实现）。

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

## 8. 检索层 `retrieval/`

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

## 9. 存储层 `storage/`

存储层负责数据持久化和检索索引，不承载复杂业务决策。

主要存储对象：

- `event_store`：原始或标准化事件，用于回放、调试和评测。
- `memory_core_store`：统一记忆主表，保存跨领域公共字段。
- domain memory store：持久化各领域 `models.py` 中定义的结构化 memory 字段。
- `embedding_store`：保存向量索引和语义检索信息。
- `access_log_store`：保存检索命中、采纳、反馈等访问记录。
- `review_schedule_store`：保存复习计划和下一次提醒时间。
- `source_state_store`：Source 层轻量处理状态（书签/游标/指纹），独立 DB，供 source adapter 追踪外部资源处理进度。

存储层原则：

- 只处理持久化、读取、索引和基础查询。
- 复杂生命周期决策应放在 `core/`。
- 领域特定结构应通过 domain memory store 扩展，不污染统一 memory core。
- 领域 dataclass/model 定义放在 `domains/*/models.py`；storage 复用这些模型完成数据库交互，不在 store 内重新定义业务模型。
- API、core、retrieval 应通过明确接口访问存储，而不是直接依赖文件或数据库细节。

## 10. LLM 层 `llm/`

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

## 11. Schema 层 `schemas/`

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

## 12. 后台任务层 `jobs/`

后台任务层处理不适合阻塞 API 请求的长期任务。

典型任务：

- `review_scan.py`：扫描需要复习、提醒或主动推送的记忆。
- `decay_compaction.py`：处理低活跃记忆的衰减、归档和压缩。
- `benchmark_runner.py`：执行评测任务并保存结果。

后台任务不直接暴露给插件，应通过 API 或 core service 提供触发和查询能力。

## 13. 核心数据流

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

## 14. 关键数据概念

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

## 15. 模块边界约束

- 插件层只做接入和注入，不做长期记忆治理。
- API 层只做协议边界，不直接写复杂业务逻辑。
- core 层负责业务编排和生命周期策略。
- domain 层负责领域内抽取、召回、排序。
- retrieval 层负责跨领域检索管线。
- storage 层负责持久化和索引，不做 admission、dedup、supersede 决策。
- llm 层负责模型调用封装，不绑定具体业务流程。
- schemas 层定义协议，不依赖业务实现。
- sources 层负责外部平台接入和标准化，不做长期记忆治理，core/domain/storage 不反向依赖 sources。

## 16. Agent 接手时的阅读顺序

为了快速理解架构，建议按以下顺序阅读：

1. `memory-bank/architecture.md`：系统分层和边界。
2. `memory-bank/prd.md`：产品目标和用户价值。
3. `docs/DEVELOPMENT PLAN.md`：模块规划和文件职责。
4. `docs/Memory Structure and Storage.md`：记忆结构和存储设计。
5. `src/retrieval/`：检索管线实现。
6. `src/storage/`：存储接口和实现。
7. `src/schemas/`：共享数据协议。
