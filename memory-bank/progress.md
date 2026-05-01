# 进度记录

## 已完成

- 明确项目定位：飞书 AI 比赛 OpenClaw 赛道参赛项目，课题为“企业级长程协作 Memory 系统”。
- 明确技术路线：OpenClaw TypeScript 插件 + 本地 Python Memory Engine。
- 插件调用链已从 mock 输出 log 推进到真实后端 HTTP 调用阶段。
- 已实现 Python Memory Engine 的 `src/app/` 基础层：
  - `config.py`
  - `logging.py`
  - `dependencies.py`
  - `main.py`
- 已新增 `requirements.txt`，包含当前最小依赖 `fastapi`、`uvicorn`、`pytest`。
- 已新增 `tests/unit/app/`，覆盖配置解析、日志中间件、依赖缓存、FastAPI app factory 和内置 `/health`。
- 已实现 Python Memory Engine 的 `src/api/` 基础层：
  - `health.py`
  - `ingest.py`
  - `retrieve.py`
  - `update.py`
  - `proactive.py`
  - `benchmark.py`
- 已新增 API schema：
  - `src/schemas/ingest.py`
  - `src/schemas/retrieve.py`
  - `src/schemas/update.py`
  - `src/schemas/proactive.py`
  - `src/schemas/benchmark.py`
- 已新增 `tests/unit/api/`，覆盖 health、ingest、retrieve、update、proactive、benchmark。
- 已实现 Python Memory Engine 的 `src/utils/` 基础工具层：
  - `ids.py`
  - `time.py`
  - `text.py`
  - `jsonlog.py`
- 已新增 `tests/unit/utils/`，覆盖 ID、UTC 时间、文本清洗和 JSON 日志工具。
- 已实现 Python Memory Engine 的 `src/core/` 基础编排层：
  - `router.py`
  - `memory_core.py`
  - `admission_control.py`
  - `dedup_merge.py`
  - `supersede.py`
  - `decay.py`
  - `access_tracker.py`
  - `scheduler.py`
  - `service.py`
- 已新增 `tests/unit/core/`，覆盖路由、生命周期、准入、去重合并、覆盖、衰减、访问记录、调度和统一服务。
- 已实现第一个比赛主线领域 `src/domains/project_decision/`：
  - `models.py`
  - `extractor.py`
  - `retriever.py`
  - `ranker.py`
  - `versioning.py`
- 已新增 `tests/unit/domains/project_decision/`，覆盖项目决策模型互转、规则抽取、领域检索、排序和版本覆盖链路。
- 已补齐后端最小服务闭环：
  - `MemoryService.ingest_event()` 已接入 `ProjectDecisionExtractor` 和 `ProjectDecisionVersionManager`。
  - `src/app/dependencies.py` 已提供 `get_memory_service()`。
  - `src/api/ingest.py`、`src/api/retrieve.py`、`src/api/update.py` 已改为通过 `MemoryService` 执行核心链路。
  - 已验证 `ingest -> MemoryCore -> retrieve` 可通过 HTTP 服务跑通。
- 已实现方向 D `team_retention` 团队知识断层与遗忘预警最小闭环：
  - `src/storage/team_retention_store.py` 在 store 层定义 `TeamRetentionMemory`，并提供 `TeamRetentionStore` 管理 `memory_team_retention` 和 `memory_review_schedule`。
  - `src/domains/team_retention/` 已实现规则抽取、领域召回、排序和版本覆盖判断。
  - `MemoryService.ingest_event()` 已接入 `TeamRetentionExtractor`、`TeamRetentionStore` 和 `TeamRetentionVersionManager`。
  - `MemoryService.proactive_suggestions()` 已可基于复习计划输出 `review_reminder`。
  - `MemoryService.update_memory()` 已支持 `reviewed` 和 `snooze`，用于推进遗忘曲线复习计划。
  - `src/api/proactive.py` 已接入 `MemoryService`，支持 team/project/workspace/now 过滤。
  - 已补强方向 D 的安全与边界：team_retention 路由优先级高于 project_decision 显式保留消息；团队检索必须带 scope；MemoryCore fallback 默认不返回无 scope 的团队记忆；版本覆盖要求项目/团队/工作区维度一致；自动 version_group 使用更细的客户/事项标识；重复注入会强化复习计划；后台 `Scheduler.scan_review_due()` 已接入团队复习提醒；复习提醒支持提前预警窗口；更新不存在 memory 会报错；API key/token/password 等敏感值会掩码后存储和推送。
- 已重构 core 与 domain 的协作边界：
  - 新增 `src/core/domain_handler.py`，定义 `MemoryDomainHandler`、`DomainRuntime`、`DomainIngestResult` 和 `DomainUpdateResult`。
  - `MemoryService` 不再直接 import `src.domains.*`，也不再在 ingest/retrieve 中硬编码 project/team 的 if/elif 分支。
  - `project_decision` 和 `team_retention` 分别提供 `ProjectDecisionDomainHandler`、`TeamRetentionDomainHandler`，领域抽取、召回、排序和版本覆盖逻辑留在 domain 内。
  - `src/app/dependencies.py` 作为应用装配层负责注册 domain handlers，后续新增 domain 只需实现 handler 并在装配层注册。
- 已收紧 TeamRetention 的 domain/storage 边界：
  - `TeamRetentionMemory`、`TeamReviewSchedule` 和保留类型定义已迁移到 `src/domains/team_retention/models.py`。
  - `src/storage/team_retention_store.py` 只保留 SQLite 表结构、写入、读取、查询、复习计划更新和行转换。
  - `src/domains/team_retention/handler.py` 继续负责领域写入编排、重复强化、版本覆盖、复习提醒和领域更新动作。
  - `memory-bank/architecture.md` 已补充 `handler.py` 架构职责，并将 domain payload 表述统一为 domain memory。
  - `memory-bank/architecture.md` 已将 `cli_workflow`、`personal_preference` 也补齐为包含 `handler.py` 的标准 domain 结构。
- 已处理 retrieve 链路 async 边界：
  - `MemoryService.retrieve_async()` 成为异步主实现，直接 `await IntentAnalyzer`、`QueryRewriter` 和 `Reranker`。
  - `MemoryService.retrieve()` 保留为同步兼容包装，供 CLI、同步测试和脚本使用。
  - `/api/v1/retrieve` 与 `/api/v1/memories/search` 已改为 FastAPI async endpoint，并调用 `await memory_service.retrieve_async(...)`。
- 已更新根目录 `README.md`，写入后端安装、测试、启动和手工验证步骤。
- 已更新 OpenClaw 插件链路：
  - hook 从 `before_agent_reply` 调整为 `before_prompt_build`。
  - `before_prompt_build` 会把当前用户消息写入后端 `/api/v1/ingest`，再调用 `/api/v1/retrieve` 获取记忆并返回 prompt 注入字段。
  - `agent_end` 会把 Agent 回复作为事件写回后端。
  - 插件日志已补充后端 HTTP 请求、状态码和响应体输出。
- 已补充后端文件日志：
  - `src/app/logging.py` 会在应用启动时写入 `logs/larkmemory.log`。
  - 可通过 `LARKMEMORY_LOG_DIR` 和 `LARKMEMORY_LOG_FILE` 覆盖日志目录与文件名。
  - `logs/` 已加入 `.gitignore`，避免运行日志进入版本库。
- 已补充后端函数级链路日志：
  - ingest 链路覆盖 API 入口、`MemoryService.ingest_event()`、事件写入、领域路由、项目决策抽取、`ProjectDecision.to_memory_core()` 和 MemoryCore 写入。
  - retrieve 链路覆盖 API 入口、`MemoryService.retrieve()`、active memory 加载、候选构造、`Reranker.rerank()` 和访问记录。
  - 日志字段包含 `event_id`、`query_id`、`memory_id`、`domain`、`candidate_count`、`result_count` 等调试关键字段。
- 已清理 API 层可复用工具：
  - `src/api/ingest.py` 复用 `src.utils.ids.event_id()` 和 `src.utils.time.utc_now_iso()`。
  - `src/api/benchmark.py` 复用 `src.utils.ids.benchmark_run_id()`。
  - 删除 `src/api/retrieve.py` 中已不再调用的旧 fallback 检索 helper 和本地 query ID 生成逻辑。
- 仓库已有基础 Python 模块：
  - `src/schemas/`
  - `src/storage/`
  - `src/retrieval/`
  - `src/llm/`
- 仓库已有对应单元测试目录。
- 已按指定结构建立 `AGENTS.md` 和 `memory-bank/` 长期上下文文档。
- 已补强 LLM provider 抽象与 OpenAI 依赖：
  - `requirements.txt` 已加入 `openai`。
  - `LLMClient` 构造参数已改为依赖 `LLMProvider` 抽象，保留 `from_openai_compatible()` 工厂。
  - `LLMClient.ajson()` 已明确异常契约：JSON 解析失败或非 object 响应统一抛出 `LLMJSONDecodeError`，并保留原始 content/cause 便于调试。
  - 已新增 OpenAI provider 单测，使用 fake SDK client 覆盖请求参数、响应解析和模型必填校验。
- 已修复 DeepSeek OpenAI-compatible JSON Output 兼容：
  - `LLMClient.atext()` 恢复为返回 `LLMResponse.content` 字符串，避免 `ajson()` 收到 `LLMResponse` 对象。
  - `OpenAIProvider` 会识别 `https://api.deepseek.com`，DeepSeek 下 `ajson()` 统一使用 `response_format={"type":"json_object"}`。
  - 普通 OpenAI-compatible base URL 继续使用 `json_schema`。
  - SDK 响应 content 仍统一在 provider 内从 `choices[0].message.content` 提取，业务 ingest/router/extractor 不直接绑定 SDK 响应结构。
- 已将事件级长期记忆准入迁入 `AdmissionController.evaluate_event()`：
  - `MemoryService.ingest_event()` 不再单独维护 `_should_extract_long_term_memory()`。
  - `AdmissionController` 在注入 LLM 时执行 `should_extract` 判断，失败时降级到规则准入。
  - `MemoryService` 会使用 `AdmissionDecision.admitted` 截断非长期记忆事件，保留事件写入但不进入 domain handler。
- 已收敛 `project_decision` 领域模型为历史决策卡片：
  - 移除复杂子对象 `DecisionAlternative`、`DecisionReason`，改为 `reasons`、`objections`、`alternatives` 字符串列表。
  - 保留项目/团队/工作区/线程、主题、结论、阶段、时间点、来源、状态、置信度、重要性和覆盖关系等主链路字段。
  - `ProjectDecision` 每个字段已补充注释，说明字段职责。
  - 修复 payload-only 决策事件抽取回归，重新从 title/content/payload/raw_payload 汇总文本。
- 已简化 ingest 链路日志 message：
  - 删除日志文本中的 `function=...` 前缀，保留 `action=...` 和关键字段。
  - 依赖 logger 名称展示文件/模块来源，降低日志正文噪音。
- 已简化 retrieve 链路 LLM 前处理：
  - `IntentAnalyzer` 的 LLM 路径从复杂 JSON schema 改为四分类纯文本标签，只输出 `cli_workflow`、`project_decision`、`personal_preference` 或 `team_retention`。
  - `QueryRewriter` 的 LLM 路径从结构化 JSON 改为只输出一条改写后的检索语句。
  - topic、时间窗口、scope filter 和 boost signal 继续由规则补齐，降低小模型输出复杂结构的失败概率。
- 已更新 `AGENTS.md`：以后读取项目文档必须显式指定 UTF-8 编码。

## 进行中

- 拆解 Python Memory Engine 的实现任务。
- 明确记忆系统的 domain、存储、检索和生命周期治理边界。
- 将白皮书、Demo 和自证评测报告的要求映射到代码实现计划。
- 准备将 `ProjectDecisionRetriever` 进一步接入统一检索编排，并完善 proactive 历史决策卡片输出。
- 后续 app/API 层可逐步迁移到 `src/utils/` 的 ID、时间、文本和 JSON 日志工具，但当前阶段未强制重构既有模块。
- 方向 D 下一步可补充 benchmark 场景，验证大量无关事件后仍能召回团队保留记忆，并验证旧版本不会继续提醒。

## 下一步建议

1. 基于已完成的 core 层，将 API 的 ingest/retrieve/update/proactive 逐步迁移为调用 `MemoryService`。
2. 定义第一阶段最小记忆闭环：
   - ingest 一个 `NormalizedEvent`
   - 生成或写入 `MemoryCore`
   - 可按条件 retrieve
   - 有测试覆盖
3. 将 `ProjectDecisionRetriever` 接入 `MemoryService.retrieve()` 或领域编排入口，替换当前 `MemoryCore` fallback 召回。
4. 将 proactive 接入 `ProjectDecisionRetriever.retrieve_cards()`，输出历史决策卡片。
5. 增加 HTTP 层矛盾更新示例和测试，证明旧记忆失效、新记忆生效。
6. 为方向 D 增加 benchmark：团队关键事项 + 大量无关事件 + 到期复习提醒 + 版本覆盖。
7. 设计本地 API 边界，再连接插件 mock 链路。
6. 设计抗干扰 benchmark，证明大量无关事件后仍能召回关键记忆。
7. 继续验证 OpenClaw 插件在真实飞书机器人消息触发时的事件字段，并按真实字段完善上下文映射。
## 风险与注意事项

- 记忆系统容易过早复杂化，应保持小步可验证。
- 公共 schema 变更影响面大，必须同步测试。
- domain 逻辑不要侵入统一 MemoryCore 生命周期治理。
- 检索排序需要避免把不同 domain 混成一个不可解释的大排序。
- 暂不接真实飞书 API，避免过早被外部集成复杂度牵引。
- 比赛最终需要交付白皮书、Demo 和评测报告，代码实现要能支撑叙事和数据证明。

## 最近验证

- `pytest tests/unit/app -q`：24 passed。
- `pytest tests/unit/api -q`：20 passed。
- `pytest tests/unit/api tests/unit/core/test_service.py tests/unit/storage tests/unit/domains/project_decision tests/unit/retrieval -q`：73 passed, 1 skipped。
- `pytest tests/unit/api tests/unit/utils -q`：49 passed。
- `pytest tests/unit/utils -q`：27 passed。
- `pytest tests/unit/core -q`：33 passed。
- `pytest tests/unit/domains/project_decision -q`：21 passed。
- `python -m pytest tests/unit/storage/test_team_retention_store.py tests/unit/domains/team_retention tests/unit/core/test_service.py tests/unit/api/test_proactive_api.py tests/unit/api/test_update_api.py -q`：26 passed。
- `python -m pytest tests/unit/core/test_router.py tests/unit/domains/team_retention tests/unit/storage/test_team_retention_store.py tests/unit/core/test_service.py tests/unit/api/test_proactive_api.py tests/unit/api/test_update_api.py -q -p no:cacheprovider`：40 passed。
- `python -m pytest tests/unit/core/test_service.py tests/unit/core/test_router.py tests/unit/api/test_ingest_api.py tests/unit/api/test_retrieve_api.py tests/unit/api/test_proactive_api.py tests/unit/api/test_update_api.py -q -p no:cacheprovider`：38 passed。
- `python -m pytest tests -q -p no:cacheprovider`：177 passed, 6 subtests passed。
- `pytest tests/unit/app tests/unit/api tests/unit/core tests/unit/domains/project_decision -q`：99 passed。
- `pytest tests/unit/app tests/unit/api -q`：41 passed。
- `pytest -q`：152 passed, 1 skipped。
- `python -m compileall src tests`：通过。
- `python -m pytest tests/unit/storage/test_team_retention_store.py tests/unit/domains/team_retention tests/unit/core/test_service.py -q -p no:cacheprovider`：27 passed。
- `python -m pytest tests/unit/core/test_service.py tests/unit/api/test_retrieve_api.py -q -p no:cacheprovider`：20 passed。
- `python -m pytest tests -q -p no:cacheprovider`：190 passed, 6 subtests passed。
- HTTP 手工验证：`/health`、`/api/v1/ingest`、`/api/v1/retrieve` 通过。
- 插件轻量验证：`openclaw.plugin.json` 可解析；旧 `before_agent_reply` 和 mock 后端调用无残留。
- `python -m pytest tests\unit\llm -q -p no:cacheprovider`：6 passed。
- `python -m compileall src tests`：通过。
- `python -m pytest tests\unit\llm -q -p no:cacheprovider`：11 passed。
- `python -m pytest tests\unit\core\test_admission_control.py tests\unit\core\test_service.py -q -p no:cacheprovider`：24 passed。
- `python -m pytest tests\unit\domains\project_decision tests\unit\storage\test_graph_store.py tests\unit\core\test_service.py tests\unit\core\test_router.py tests\unit\core\test_admission_control.py tests\unit\llm -q -p no:cacheprovider`：75 passed。
- `python -m pytest tests\unit\core\test_service.py tests\unit\core\test_router.py tests\unit\domains\project_decision\test_extractor.py tests\unit\api\test_ingest_api.py tests\unit\storage\test_event_store.py tests\unit\storage\test_memory_core_store.py -q -p no:cacheprovider`：46 passed。
- `python -m pytest tests\unit\domains\project_decision tests\unit\core\test_service.py tests\unit\api\test_ingest_api.py tests\unit\storage\test_event_store.py tests\unit\storage\test_memory_core_store.py -q -p no:cacheprovider`：56 passed。
- `uv run pytest tests\unit\retrieval\test_retrieval_components.py -q`：12 passed。
- `uv run python -m compileall src tests`：通过。
- `uv run pytest tests\unit\retrieval tests\unit\api\test_retrieve_api.py tests\unit\core\test_service.py -q`：32 passed, 2 failed；失败项为旧日志断言仍期待 `function=...` 前缀。

## 2026-04-27 图数据库 Store 进展

- 已新增 `src/storage/graph_store.py`，采用 Neo4j 作为旁路 Graph Memory Index，不替代 SQLite 主存储。
- 已定义 `Neo4jGraphConfig` 和 `Neo4jGraphStore`，支持 Neo4j 约束/索引初始化、Memory 节点写入、Entity 关系写入、Project/Team/Workspace/User 上下文关系写入、版本覆盖关系写入。
- 已提供三类示例查询：`get_version_chain()`、`find_memories_by_entity()`、`find_project_context()`。
- 已新增 `tests/unit/storage/test_graph_store.py`，通过 fake driver 验证 Cypher、参数和查询返回，不依赖本机 Neo4j 服务。
- 已在 `requirements.txt` 增加 `neo4j` Python driver。
- 验证：`python -m pytest tests\unit\storage -q -p no:cacheprovider`，27 passed。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，184 passed, 6 subtests passed。
- 已补充显式 `Decision` 图模型：`Decision` 节点约束/索引、`upsert_project_decision()`、`MADE_DECISION`、`RECORDED_AS`、`BELONGS_TO`、`find_decisions_by_user()` 和 `find_project_decisions()`。
- 验证：`python -m pytest tests\unit\storage -q -p no:cacheprovider`，32 passed。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，189 passed, 6 subtests passed。

## 2026-04-28 飞书 Source Adapter 架构进展

- 已在 `memory-bank/architecture.md` 增加飞书 Source Adapter 分层设计，明确 `client/`、`events/`、`proactive/` 三层边界。
- 已新增 `src/sources/feishu/client/`：
  - `config.py` 读取 `LARKMEMORY_FEISHU_*` 应用凭证与运行配置，`APP_ID/APP_SECRET` 定位为飞书企业自建应用凭证，不是用户登录态。
  - `sdk.py` 懒加载 `lark-oapi`，封装 OpenAPI client 和 WebSocket client 创建。
  - `listener.py` 作为 WebSocket source worker 入口，注册消息事件和卡片回调，并委托 events/proactive 层处理。
- 已新增 `src/sources/feishu/events/`：
  - `models.py` 定义 `FeishuMessageEvent`、`FeishuCardActionEvent`、`FeishuEventEnvelope`。
  - `normalizer.py` 将飞书 IM 消息标准化为现有 `NormalizedEvent`，当前将 `chat_id` 映射到 `EventContext.team_id` 并保留在 payload 中。
  - `dispatcher.py` 调用 `MemoryService.ingest_event()`，并容忍飞书重试导致的重复事件。
- 已新增 `src/sources/feishu/proactive/`：
  - `cards.py` 将 `review_reminder` suggestion 渲染为飞书 interactive card JSON。
  - `notifier.py` 封装 `im.v1.message.create` 发送文本和互动卡片。
  - `callbacks.py` 将卡片按钮 `reviewed`、`snooze`、`expire`、`forget` 映射到 `MemoryService.update_memory()`。
- 已在 `requirements.txt` 增加 `lark-oapi`，用于真实飞书 WebSocket 监听、消息发送和卡片交互。
- 已新增 `tests/unit/sources/feishu/`，覆盖飞书消息标准化、事件分发入 core、重复事件容忍、复习卡片构造和卡片按钮动作映射。
- 验证：`python -m pytest tests\unit\sources\feishu -q -p no:cacheprovider`，7 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，197 passed, 6 subtests passed。

## 2026-04-30 TeamRetention LLM 抽取与向量索引进展

- 已将 D 方向团队留存记忆链路从 `TeamRetentionDomainHandler` 内部扩展为“规则预处理 + 单次 LLM 结构化抽取 + 后端准入复核 + 生命周期解析 + 向量索引”。
- 新增 `src/domains/team_retention/preprocessor.py`，负责事件文本清洗、敏感信息脱敏、显式记忆/风险/未来依赖等规则特征提取；规则不再作为进入抽取前的硬过滤。
- 新增 `src/domains/team_retention/llm_extractor.py`，复用现有 `LLMClient.ajson()` 完成一次 JSON schema 结构化调用，输出 `reject`、`candidate` 或 `active` 建议以及 `score_breakdown`。
- 新增 `src/domains/team_retention/admission.py`，用固定权重在后端重新计算 `team_retention_score`，并将 LLM 的状态建议复核为最终 `reject`、`candidate` 或 `active`。
- 新增 `src/domains/team_retention/embedding.py`，封装 `TeamRetentionEmbeddingIndexer`，将 `candidate` 和 `active` 团队记忆写入 `EmbeddingStore`，metadata 包含 domain、status、team/project/workspace、fact_type、risk_level 和 version_group。
- 新增 `src/domains/team_retention/lifecycle.py`，在入库前结合关系库 `version_group` 精确候选和向量相似候选，识别强化或冲突；相似但事实变更且无明确覆盖信号时，新记忆降级为 `candidate` 并标记 `conflict_with`，不创建复习计划。
- 已扩展 `DomainRuntime`，向 domain handler 传入可选 `embedding_store`；`MemoryService.ingest_event()` 已将自身的 `embedding_store` 注入运行时。
- `TeamRetentionRetriever` 已支持默认召回 `active + candidate`，并在返回结果 extra 中标记 `status` 和 `needs_confirmation`；主动提醒仍只依赖 active 记忆的 review schedule。
- `requirements.txt` 已增加 `chromadb`，用于启用真实 Chroma 向量存储。
- 已补充 `tests/unit/domains/team_retention/test_handler_llm_embedding.py`，覆盖 LLM candidate/active/reject、向量写入、active 创建复习计划、candidate 不提醒、向量相似冲突降级 candidate。
- 验证：`python -m pytest tests/unit/domains/team_retention tests/unit/storage/test_team_retention_store.py tests/unit/core/test_service.py tests/unit/storage/test_embedding_store.py tests/unit/llm/test_client.py -q -p no:cacheprovider`，44 passed。
- 验证：`python -m pytest tests/unit/api tests/unit/app -q -p no:cacheprovider`，47 passed。
- 验证：`python -m pytest tests/unit/core tests/unit/domains tests/unit/storage tests/unit/retrieval tests/unit/llm tests/unit/sources/feishu/test_events.py tests/unit/sources/feishu/test_proactive.py tests/unit/sources/feishu/test_listener.py tests/unit/utils -q -p no:cacheprovider`，177 passed, 6 subtests passed。
- 验证：`python -m pytest tests -q -p no:cacheprovider --ignore=tests/unit/sources/feishu/test_chat_list_demo.py --ignore=tests/unit/sources/feishu/test_cli_demo.py`，224 passed, 6 subtests passed。
- 验证：`python -m compileall src tests`，通过。
- 注意：直接运行 `python -m pytest tests -q -p no:cacheprovider` 仍会因仓库缺失 `lark-oapi-demo/chat_list_demo.py` 和 `lark-oapi-demo/cli_demo.py` 在 collection 阶段失败；该问题与本次 D 方向链路改动无关。

## 2026-04-30 TeamRetention 审查反馈修复

- 修复 candidate 重复强化问题：candidate 不再调用依赖 review schedule 的 `reinforce_review()`；无 schedule 的候选记忆会更新 metadata 中的 `reinforce_count` 和 `last_reinforced_at`，保持“可召回但不提醒”的语义。
- 修复 LLM 生命周期覆盖问题：`TeamRetentionLifecycleResolver` 已识别“现在、改为、更新为、替换、不再、旧、不用、以后按”等明确覆盖信号；命中时走 `supersede`，旧记忆标记为 `superseded`，旧 review schedule 停用，新 active 记忆创建新 schedule。
- 修复 LLM prompt 敏感 payload 问题：LLM user prompt 中的 payload 会递归脱敏，不再原样发送 API key/token/secret/password 等敏感值。
- 修复 Chroma metadata 真实环境隐患：`TeamRetentionEmbeddingIndexer.build_metadata()` 会过滤 `None` 值，避免真实 Chroma 拒绝 metadata。
- 修复飞书 listener 启动路径：`main()` 调用 `build_event_handler(settings=settings)`，真实 WebSocket 启动时会使用配置中的 verification token 和 encrypt key。
- 新增回归测试覆盖：重复 candidate 强化、明确 supersede、LLM prompt payload 脱敏、embedding metadata 过滤 None、listener main 传 settings。
- 验证：`python -m pytest tests/unit/domains/team_retention/test_handler_llm_embedding.py tests/unit/sources/feishu/test_listener.py -q -p no:cacheprovider`，11 passed。
- 验证：`python -m pytest tests/unit/domains/team_retention tests/unit/storage/test_team_retention_store.py tests/unit/core/test_service.py tests/unit/storage/test_embedding_store.py tests/unit/llm/test_client.py tests/unit/sources/feishu/test_listener.py -q -p no:cacheprovider`，51 passed。
- 验证：`python -m pytest tests/unit/core tests/unit/domains tests/unit/storage tests/unit/retrieval tests/unit/llm tests/unit/sources/feishu/test_events.py tests/unit/sources/feishu/test_proactive.py tests/unit/sources/feishu/test_listener.py tests/unit/utils tests/unit/api tests/unit/app -q -p no:cacheprovider`，229 passed, 6 subtests passed。
- 验证：`python -m pytest tests -q -p no:cacheprovider --ignore=tests/unit/sources/feishu/test_chat_list_demo.py --ignore=tests/unit/sources/feishu/test_cli_demo.py`，229 passed, 6 subtests passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-04-30 TeamRetention 追加审查反馈修复

- 修复 LLM 失败 fallback 仍绕过原有规则能力的问题：无 LLM 和 LLM JSON/异常失败现在共用同一套 `_ingest_event_with_rules()`，该路径保留 `_find_duplicate()`、`TeamRetentionVersionManager.detect_update()` 和 `apply_supersede()`。
- 扩展明确覆盖信号判断输入：`TeamRetentionLifecycleResolver.resolve()` 现在会同时检查 `fact_value`、`evidence_text` 和脱敏后的原始事件文本，避免 LLM 将“旧值不再使用”等覆盖信号移出 `fact_value` 后误判为 conflict candidate。
- 新增回归测试覆盖：LLM 失败后规则 fallback 仍可基于显式 `version_group` 执行 supersede；覆盖信号只出现在 `evidence_text` 时也会 supersede 旧 active 记忆。
- 验证：`python -m pytest tests/unit/domains/team_retention/test_handler_llm_embedding.py::test_llm_failure_fallback_preserves_rule_version_supersede tests/unit/domains/team_retention/test_handler_llm_embedding.py::test_supersede_signal_from_evidence_text_updates_old_memory -q -p no:cacheprovider`，2 passed。
- 验证：`python -m pytest tests/unit/domains/team_retention tests/unit/storage/test_team_retention_store.py tests/unit/core/test_service.py tests/unit/storage/test_embedding_store.py tests/unit/llm/test_client.py tests/unit/sources/feishu/test_listener.py -q -p no:cacheprovider`，53 passed。
- 验证：`python -m pytest tests/unit/core tests/unit/domains tests/unit/storage tests/unit/retrieval tests/unit/llm tests/unit/sources/feishu/test_events.py tests/unit/sources/feishu/test_proactive.py tests/unit/sources/feishu/test_listener.py tests/unit/utils tests/unit/api tests/unit/app -q -p no:cacheprovider`，231 passed, 6 subtests passed。
- 验证：`python -m pytest tests -q -p no:cacheprovider --ignore=tests/unit/sources/feishu/test_chat_list_demo.py --ignore=tests/unit/sources/feishu/test_cli_demo.py`，231 passed, 6 subtests passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-01 TeamRetention 向量混合检索进展

- 修复向量索引只用于生命周期、不参与用户检索召回的问题。
- `TeamRetentionRetriever` 已新增可选 `embedding_store` 依赖，在关系库 active/candidate 候选之外调用 `EmbeddingStore.query_similar()`，按 team/project/workspace scope 过滤，形成 lexical + structured scope + vector hybrid recall。
- 向量命中会通过 `memory_id` 回表加载 `MemoryCore` 和 `TeamRetentionMemory`，继续复用现有 `MemoryItem`、`RankedMemory` 和 `TeamRetentionRanker` 输出，不新增独立检索结果模型。
- 检索结果会在 `matched_fields` 和 `MemoryItem.extra` 标记 `vector_similarity`，该分数参与领域内 ranker 的 relevance 分。
- `TeamRetentionDomainHandler` 已接收可选 `embedding_store` 并传给 `TeamRetentionRetriever`；`src/app/dependencies.py` 已将 `get_embedding_store()` 注入 handler，确保应用装配路径也启用向量检索。
- 新增测试覆盖：`TeamRetentionRetriever` 调用向量 store、按 scope 过滤、合并 vector hit；`get_memory_service()` 将 embedding store 接到 team_retention retriever。
- 验证：`python -m pytest tests/unit/domains/team_retention tests/unit/app/test_dependencies.py tests/unit/core/test_service.py tests/unit/storage/test_embedding_store.py -q -p no:cacheprovider`，51 passed。
- 验证：`python -m pytest tests/unit/core tests/unit/domains tests/unit/storage tests/unit/retrieval tests/unit/llm tests/unit/sources/feishu/test_events.py tests/unit/sources/feishu/test_proactive.py tests/unit/sources/feishu/test_listener.py tests/unit/utils tests/unit/api tests/unit/app -q -p no:cacheprovider`，233 passed, 6 subtests passed。
- 验证：`python -m pytest tests -q -p no:cacheprovider --ignore=tests/unit/sources/feishu/test_chat_list_demo.py --ignore=tests/unit/sources/feishu/test_cli_demo.py`，233 passed, 6 subtests passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-01 TeamRetention 准入与覆盖策略优化

- 已将 D 方向 LLM 链路进一步收敛为“语义抽取器”角色：LLM prompt 改为中文业务抽取提示，不再要求模型输出重要性 score、最终 active/candidate/reject 裁决或复习计划判断。
- `TeamRetentionLLMExtractor` 已支持新的语义抽取 JSON：`is_team_retention_candidate`、`certainty`、`stability`、`actionability`、`update_intent`、`update_signal_text`、`needs_confirmation`、`evidence_text` 等；旧字段仍保持兼容。
- prompt 不再传真实内部 ID：`event_id`、`team_id`、`project_id`、`workspace_id`、`thread_id` 保留在后端治理链路，LLM 只看到 `has_team_scope`、`has_project_scope` 等业务 hint。
- 敏感信息处理从 prompt 文案中移到后端 `TeamRetentionSensitivePolicy`，当前默认对 LLM 输入脱敏，后续可切换 `raw`、`mask_for_llm`、`mask_all` 策略。
- `TeamRetentionAdmissionDecider` 不再依赖 LLM 自评分加权，而是用后端可解释规则综合 LLM 抽取、证据、scope、fact 类型、规则弱提示和不确定性 blocker 计算最终准入。
- `rule_features` 已明确作为弱提示：为空不会直接否定团队记忆价值；关键词命中也不会直接提升为 active。
- candidate/active 边界进一步收紧：candidate 可以入库和入向量库并被检索召回，但始终标记 `needs_confirmation`，不创建 review schedule；active 才创建 review schedule 并参与主动提醒。
- `TeamRetentionLifecycleResolver` 覆盖策略更保守：只有新记忆最终为 active、非待确认、同 scope/同 fact_type/同实体或 version_group、存在明确覆盖信号时，才允许 supersede 旧 active；candidate 或不确定更新只会作为 conflict candidate 保留旧 active。
- 检索测试补强 candidate 注入标记，确保召回结果带 `status=candidate` 和 `needs_confirmation=true`。
- 新增回归测试覆盖：LLM 无 score/importance 仍可准入、rule_features 为空但原文有长期价值、规则关键词误命中普通聊天不能 active、speculative/needs_confirmation 不能 active、prompt 不暴露内部 ID、敏感策略不硬编码在 prompt、candidate 更新不能 supersede、active 明确更新才能 supersede。
- 验证：`python -m pytest tests/unit/domains/team_retention/test_handler_llm_embedding.py tests/unit/domains/team_retention/test_retriever.py -q -p no:cacheprovider`，22 passed。
- 验证：`python -m pytest tests/unit/domains/team_retention tests/unit/storage/test_team_retention_store.py tests/unit/core/test_service.py tests/unit/storage/test_embedding_store.py tests/unit/app/test_dependencies.py -q -p no:cacheprovider`，62 passed。

## 2026-05-01 TeamRetention lifecycle 与 LLM schema 补充修复

- 收紧 `TeamRetentionLifecycleResolver` 的自动覆盖判定：非精确 `version_group` 不再只靠共享客户/实体片段通过，必须能解析出同一实体和同一事实槽位；不同主题的向量相似命中只会进入 conflict/new 链路，不会误 supersede 旧 active。
- 修复新 active 被旧 candidate 降级的问题：满足严格 supersede 条件时，新记忆最终状态使用后端 admission status，不再由旧记忆状态决定。
- 清理 TeamRetention LLM JSON schema 主契约：`decision`、`score_breakdown`、`importance`、`confidence` 不再出现在结构化调用 schema 中；`from_dict()` 仍容忍旧字段输入，但 admission 不依赖这些旧字段。
- 新增回归测试覆盖：同客户不同事实槽位不能覆盖、旧 candidate 不能拖低新 active、schema 不暴露旧裁决字段、旧字段兼容但不影响 admission、prompt 明确 LLM 不做最终准入/打分/复习计划/覆盖裁决。
- 验证：`python -m pytest tests/unit/domains/team_retention -q -p no:cacheprovider`，34 passed。
- 验证：`python -m compileall src/domains/team_retention tests/unit/domains/team_retention`，通过。
