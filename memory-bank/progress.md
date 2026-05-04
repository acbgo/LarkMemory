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
- 飞书 API 已接入真实 WebSocket 消息监听、消息发送和卡片交互，需持续关注集成稳定性。
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
- 继续收紧 LLM 兼容边界：`TeamRetentionLLMExtraction` 不再保存 `decision`、`score_breakdown`、`importance`、`confidence` 旧裁决字段；旧字段只在 `from_dict()` 输入层被容忍，不再进入 handler metadata 或 admission 输出。
- 已迁移 TeamRetention LLM 单测夹具，普通路径统一使用 semantic response，删除旧 `_llm_response` 测试 helper。
- 验证：`python -m pytest tests/unit/domains/team_retention -q -p no:cacheprovider`，34 passed。

## 2026-05-01 Benchmark 数据集整理

- 已将外部 `Memory-Benchmark-main` 数据集整理为当前项目根目录下的 `benchmark/`。
- 保留 4 个方向 JSONL 数据集、`schema.json`、指标说明、报告模板、Memory Engine 适配说明和格式校验脚本。
- 移除生成期和非必要资产：生成脚本、mock runner、pycache、benchmark 生成计划文档。
- 清洗 JSONL 中与 schema 不一致的冗余字段：移除 `decision`、`reason`、`rejected_option`，将 `latest_value` 统一为 `current_value`。
- `schema.json` 已补充 `baseline_steps` 和 `actual_steps`，用于步骤节省类效能验证。
- `validate_schema.py` 已改为标准库校验，显式 UTF-8 读取文件，并修正矛盾更新检查字段。
- 验证：`python benchmark\scripts\validate_schema.py`，49/49 passed, 0 failed；保留 16 条 hard case 噪声数量建议 warning。

## 2026-05-03 Embedding API Provider 进展

- 已新增 LLM 层 embedding 抽象：
  - `src/llm/embedding_base.py` 定义 `EmbeddingProvider` 协议和 `EmbeddingResponse`。
  - `src/llm/embedding_client.py` 作为业务统一入口，负责输入清洗和单条/批量 embedding 调用。
  - `src/llm/openai_compatible_embedding_provider.py` 调用 OpenAI-compatible `/embeddings` API，支持 `model`、`base_url`、`dimensions` 和 `encoding_format`。
- 已新增 embedding HTTP API：
  - `POST /api/v1/embeddings`：单文本向量化。
  - `POST /api/v1/embeddings/batch`：批量文本向量化。
  - `src/schemas/embeddings.py` 定义请求和响应 schema。
- 已扩展 app 配置和依赖注入：
  - 新增 `LARKMEMORY_EMBEDDING_PROVIDER`、`LARKMEMORY_EMBEDDING_API_KEY`、`LARKMEMORY_EMBEDDING_MODEL`、`LARKMEMORY_EMBEDDING_BASE_URL`、`LARKMEMORY_EMBEDDING_DIMENSIONS`、`LARKMEMORY_EMBEDDING_ENCODING_FORMAT` 等配置。
  - `get_embedding_client()` 在 `LARKMEMORY_ENABLE_EMBEDDING=true` 且配置完整时创建 `EmbeddingClient`。
  - `MemoryService` 和 `DomainRuntime` 已接收可选 `embedding_client`。
- 已改造 TeamRetention 向量链路：
  - 写入索引时优先通过 `EmbeddingClient.embed_text()` 生成显式向量，再写入 Chroma。
  - 检索时优先通过 query embedding 调用 `EmbeddingStore.query_by_embedding()`；未配置 client 时保留原 `query_texts` fallback。
  - 生命周期相似记忆判断也可复用显式 query vector。
- 已补充测试：
  - `tests/unit/llm/test_embedding_client.py`
  - `tests/unit/llm/test_openai_compatible_embedding_provider.py`
  - `tests/unit/api/test_embeddings_api.py`
  - `tests/unit/domains/team_retention/test_retriever.py` 中新增 query vector 检索覆盖。
  - `tests/unit/app/test_dependencies.py` 中新增 embedding client 装配覆盖。
- 验证：`python -m pytest tests\unit\llm\test_embedding_client.py tests\unit\llm\test_openai_compatible_embedding_provider.py tests\unit\api\test_embeddings_api.py tests\unit\domains\team_retention\test_retriever.py -q -p no:cacheprovider`，12 passed。
- 验证：`python -m pytest tests\unit\app\test_dependencies.py tests\unit\app\test_config.py tests\unit\api\test_embeddings_api.py tests\unit\llm\test_embedding_client.py tests\unit\llm\test_openai_compatible_embedding_provider.py tests\unit\domains\team_retention\test_retriever.py -q -p no:cacheprovider`，28 passed。
- 验证：`python -m pytest tests\unit\app tests\unit\api tests\unit\llm tests\unit\domains\team_retention tests\unit\core\test_service.py -q -p no:cacheprovider`，121 passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-03 本地 Embedding Provider 进展

- 已新增 `src/llm/local_sentence_transformers_embedding_provider.py`，支持从本地模型目录加载 SentenceTransformers-compatible embedding 模型。
- 本地 provider 支持配置：
  - `LARKMEMORY_EMBEDDING_PROVIDER=local_sentence_transformers` 或 `local`
  - `LARKMEMORY_EMBEDDING_MODEL_PATH`
  - `LARKMEMORY_EMBEDDING_DEVICE`
  - `LARKMEMORY_EMBEDDING_NORMALIZE`
  - `LARKMEMORY_EMBEDDING_BATCH_SIZE`
  - `LARKMEMORY_EMBEDDING_DIMENSIONS`
  - `LARKMEMORY_EMBEDDING_TRUST_REMOTE_CODE`
- `src/app/dependencies.py` 已在 `get_embedding_client()` 中支持按配置选择 OpenAI-compatible API provider 或本地 SentenceTransformers provider。
- `requirements.txt` 已增加 `sentence-transformers`，作为本地模型 provider 依赖。
- 本地 provider 与 API provider 共用 `EmbeddingClient`，因此 `/api/v1/embeddings`、`/api/v1/embeddings/batch`、TeamRetention 写入索引和 query vector 检索无需区分来源。
- 新增 `tests/unit/llm/test_local_sentence_transformers_embedding_provider.py`，覆盖本地模型加载参数、encode 参数、维度截断和缺依赖报错。
- `tests/unit/app/test_dependencies.py` 已补充本地 provider 依赖装配测试。
- 验证：`python -m pytest tests\unit\llm\test_local_sentence_transformers_embedding_provider.py tests\unit\app\test_dependencies.py -q -p no:cacheprovider`，15 passed。
- 验证：`python -m pytest tests\unit\llm tests\unit\app tests\unit\api tests\unit\domains\team_retention tests\unit\core\test_service.py -q -p no:cacheprovider`，125 passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-03 Embedding 容错修复

- 修复写入链路 embedding 缺少降级的问题：
  - `TeamRetentionEmbeddingIndexer.upsert()` 中显式 embedding 生成失败时只记录 warning，并继续尝试以 Chroma 文本 `documents` 方式写入索引。
  - Chroma 索引写入失败时只记录 warning，不影响 `MemoryCore`、`TeamRetentionMemory` 和 review schedule 主写入结果。
  - 生命周期相似记忆向量查询失败时返回空候选，不阻断 ingest。
- 修复检索链路缺少降级的问题：
  - `TeamRetentionRetriever._vector_hits()` 捕获 embedding client 或 Chroma 查询异常，记录 warning 后返回 `{}`。
  - 向量召回失败后继续执行已有结构化 scope 过滤和关键词/字段打分检索。
- 修复健康检查 embedding 状态不准确的问题：
  - `/health` 的 `embedding` 字段新增 `vector_store_available`、`embedding_client_available`、`provider` 和 `model`。
  - `available` 现在表示 vector store 和 embedding client 都可用。
  - `get_embedding_client()` 在 provider 初始化失败时记录 warning 并返回 `None`，避免 health 或应用装配因本地依赖缺失、模型目录不可用而直接崩溃。
- 新增回归测试覆盖：
  - embedding 索引失败不影响 team_retention 主写入。
  - 检索 query embedding 失败时回退到关键词/结构化检索。
  - health 区分 vector store 和 embedding client 状态。
  - provider 初始化失败时 embedding client 返回 unavailable。
- 验证：`python -m pytest tests\unit\app\test_dependencies.py::TestDependencies::test_get_embedding_client_returns_none_when_provider_init_fails tests\unit\domains\team_retention\test_handler_llm_embedding.py::test_embedding_index_failure_does_not_break_memory_ingest tests\unit\domains\team_retention\test_retriever.py::test_retrieve_falls_back_when_vector_embedding_fails tests\unit\api\test_health_api.py -q -p no:cacheprovider`，5 passed。
- 验证：`python -m pytest tests\unit\llm tests\unit\app tests\unit\api tests\unit\domains\team_retention tests\unit\core\test_service.py -q -p no:cacheprovider`，129 passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-03 Rerank 服务接入进展

- 已按“模型已在独立服务器部署，LarkMemory 只负责接入”的边界新增 rerank 服务客户端，不在本进程配置 GPU/device 或加载模型。
- 新增 LLM 层 rerank 抽象：
  - `src/llm/rerank_base.py` 定义 `RerankDocument`、`RerankScore`、`RerankResult`、`RerankResponse` 和 `RerankProvider`。
  - `src/llm/rerank_client.py` 负责输入校验、调用 provider 打分并按分数排序。
  - `src/llm/http_rerank_provider.py` 通过 HTTP `POST` 接入已部署 rerank 服务，支持 `results` 和 `scores` 两种常见响应格式。
- 新增 HTTP API：
  - `POST /api/v1/rerank`，输入 query、documents、top_k，输出按相关性排序的文档结果。
  - `src/schemas/rerank.py` 定义请求和响应 schema。
- 已扩展 app 配置和依赖注入：
  - 新增 `LARKMEMORY_ENABLE_RERANK`、`LARKMEMORY_RERANK_PROVIDER`、`LARKMEMORY_RERANK_BASE_URL`、`LARKMEMORY_RERANK_ENDPOINT`、`LARKMEMORY_RERANK_API_KEY`、`LARKMEMORY_RERANK_MODEL`、`LARKMEMORY_RERANK_TIMEOUT`。
  - `get_rerank_client()` 在配置完整时创建 `RerankClient`；未配置时返回 `None`。
  - `/health` 已增加 `rerank.enabled`、`rerank.available`、`rerank.provider`、`rerank.model`。
- 已检查 embedding 服务接入方式：
  - `LARKMEMORY_EMBEDDING_PROVIDER=http` 已作为 `openai_compatible` 的别名接入，适合模型在独立服务器暴露 OpenAI-compatible `/v1/embeddings` 的场景。
  - 服务器部署场景不需要配置 `LARKMEMORY_EMBEDDING_DEVICE`；该配置只属于可选的进程内模型加载路径。
- 新增测试覆盖：
  - `tests/unit/llm/test_rerank_client.py`
  - `tests/unit/llm/test_http_rerank_provider.py`
  - `tests/unit/api/test_rerank_api.py`
  - `tests/unit/app/test_dependencies.py` 中新增 rerank client 装配和 embedding `http` provider alias 覆盖。
  - `tests/unit/api/test_health_api.py` 中新增 rerank health 状态覆盖。
- 验证：`python -m pytest tests\unit\llm\test_rerank_client.py tests\unit\llm\test_http_rerank_provider.py tests\unit\api\test_rerank_api.py -q -p no:cacheprovider`，8 passed。
- 验证：`python -m pytest tests\unit\llm tests\unit\app tests\unit\api tests\unit\domains\team_retention tests\unit\core\test_service.py -q -p no:cacheprovider`，140 passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-03 Rerank API 错误映射修复

- 修复 `/api/v1/rerank` 对上游模型服务异常缺少错误映射的问题。
- `rerank_client` 不可用时仍返回 `503 rerank client is not available`。
- `rerank_client.rerank()` 调用过程中发生 HTTP 服务不可用、超时、响应解析异常或 provider/client 其他异常时，API 现在记录 warning 并返回 `502 rerank upstream failed`，避免冒泡为通用 500。
- 新增 `tests/unit/api/test_rerank_api.py::TestRerankApi::test_rerank_api_maps_upstream_failure_to_502` 覆盖。
- 验证：`python -m pytest tests\unit\api\test_rerank_api.py -q -p no:cacheprovider`，3 passed。
- 验证：`python -m pytest tests\unit\llm tests\unit\app tests\unit\api tests\unit\domains\team_retention tests\unit\core\test_service.py -q -p no:cacheprovider`，141 passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-03 服务启动配置文件

- 已在项目根目录新增本地 `larkmemory.env`，集中维护启动前需要的 `LARKMEMORY_*` 环境变量。
- 已新增 `larkmemory.env.example` 作为可提交模板，并将 `larkmemory.env` 加入 `.gitignore`，避免真实 API key 进入版本库。
- `src/app/config.py` 已支持启动时自动读取 `larkmemory.env`，也支持通过 `LARKMEMORY_CONFIG_FILE` 指定其他配置文件。
- 配置优先级为真实环境变量高于配置文件，便于临时覆盖端口、路径或模型服务地址。
- 配置文件已覆盖 app、SQLite、Chroma、日志、LLM、embedding 服务和 rerank 服务相关变量。
- README 已补充推荐启动方式：先改 `larkmemory.env`，再按原方式执行 `uvicorn`；不依赖 PowerShell/cmd 脚本。

## 2026-05-03 方向 A：CLI 工作流记忆 — 阶段 1（Domain 最小闭环）

- 已实现比赛方向 A `cli_workflow` 领域记忆的完整后端闭环：事件写入 → 模板抽取 → MemoryCore 存储 → 按用户/项目检索召回。
- 新增 `src/domains/cli_workflow/`：
  - `models.py` — `CLIWorkflowMemory`、`ParameterBinding`、`CLIWorkflowCandidate`，实现 `to_memory_core()` / `from_memory_core()` 双向转换。不新增 MemoryCore 表列，domain 数据编码进 `entities`/`tags`/`content_text`。
  - `extractor.py` — 规则抽取器：`shlex.split` token 化 → 提取基础命令名（前 3 token） → `--key value`/`--key=value`/`-x value` 参数化 → 过滤 `cd`/`ls` 等无意义命令。支持 shell 和 openclaw 两种事件源。
  - `handler.py` — `CLIWorkflowDomainHandler` 实现 `MemoryDomainHandler` 协议，编排 extract → is_admissible → version detect → store 链路。
  - `retriever.py` — 按 `user_id` 严格隔离（个人记忆），综合命令名匹配、关键词、执行频率（importance）、新鲜度（freshness_score）、成功率（confidence）多维度打分。
  - `versioning.py` — 以 `(user_id, project_id, command_name)` 为匹配键，Shell 重复执行走强化更新（累计次数+参数频率），OpenClaw 显式教学覆盖 Shell 统计。`entity_filters` 下推 SQL 过滤。
- 已在 `src/app/dependencies.py` 注册 `CLIWorkflowDomainHandler`。
- 已新增 `tests/unit/domains/cli_workflow/`，62 tests 覆盖模型互转、抽取过滤、版本覆盖、检索打分。
- 验证：`python -m pytest tests/unit/domains/cli_workflow -q`，62 passed。

## 2026-05-03 方向 A：CLI 工作流记忆 — 阶段 2（CLI 客户端工具）

- 已实现 `lark-memory` 命令行工具，提供 shell 被动监听 + Tab 补全。
- 新增 `src/sources/cli/`：
  - `main.py` — CLI 入口（argparse），5 个子命令：`hook install/uninstall/status`、`suggest`、`complete`、`completion`、`ingest`。
  - `hook.py` — shell 钩子安装/卸载，标记块（`# >>> LarkMemory hook >>>`/`# <<<`）管理，可逆幂等。bash（`trap DEBUG`+`PROMPT_COMMAND`）和 zsh（`add-zsh-hook`）双支持。hook 函数过滤自身命令（`lark-memory*`）、空命令。补全函数嵌入模板，`complete -D`（bash）/ `compdef '*'`（zsh）注册为通用回退。
  - `ingest.py` — shell hook 捕获命令后构造 `NormalizedEvent`（补齐 `payload.command`+`payload.args`），异步 POST `/api/v1/ingest`，HTTP 失败静默降级。
  - `retrieve.py` — `suggest` 和 `complete` 子命令实现，调 `POST /api/v1/retrieve`，用 `CLIWorkflowMemory.from_memory_core()` 解析 `MemoryHit` 响应（适配 API 实际返回格式，不依赖不存在的 `extra` 字段）。
  - `completion.py` — 动态生成 bash/zsh completion script。
  - `_client.py` — 公共 HTTP 客户端（`post_ingest`/`post_retrieve`），消除 `_get_api_base()` 重复定义。
- 已新增 `tests/unit/sources/cli/`，52 tests 覆盖 hook 安装/卸载/幂等、事件构造 payload 完整性、MemoryHit 解析、补全候选生成。
- 验证：`python -m pytest tests/unit/sources/cli -q`，49 passed。

## 2026-05-03 方向 A：同事审查修复（6 项问题）

- 修复 `is_admissible()` 死代码：在 `handler.py` 的 `ingest_event()` 循环中增加 `if not candidate.is_admissible(): continue`。
- 修复单字已知工具链命令（如裸敲 `npm`）绕过过滤：`extractor.py` 中 `_has_known_prefix` 后增加 `len(tokens) == 1` 判断。
- 修复 `_merge_bindings` 旧参数值频率被错误衰减：改用 `(param_name, param_value)` 做 key，历史频率只增不减，让 `freshness_score` 推高最近值。
- 提取 `_get_api_base()` 到公共模块 `_client.py`，消除 `ingest.py` 和 `retrieve.py` 中的重复定义。
- `_find_existing` 全表 O(n) 扫描下推 SQL：`MemoryCoreStore.search_memory_candidates` 新增 `entity_filters` 参数，生成 `entities_json LIKE` 条件。
- 修复 zsh `compdef -first-` 无效语法：改为 `compdef _lark_memory_complete_wrapper '*'`。

## 2026-05-03 Core 层重构：统一动态路由

- 两套路由逻辑（`Router.route_event()` 和 `IntentAnalyzer.analyze()`）各自维护关键词列表，Ingest 侧缺少 CLI 关键词导致非 `command_finished` 事件（如 OpenClaw 教学消息）路由错误。
- 新增 `src/core/domain_classifier.py` — 统一四域分类器：
  - LLM：`atext()` 四标签纯文本分类（temperature=0, max_tokens=16），输出 `cli_workflow`/`project_decision`/`personal_preference`/`team_retention`。
  - 硬规则：`command_finished`/`command_failed` → `cli_workflow`（0ms 直接返回）。
  - 关键词降级：统一的 4 域 × ~20 词列表（合并自 Router + IntentAnalyzer），含 CLI 关键词（`--` flag 模式、部署/build/命令等）。
  - `classify()` async 入口（供 IntentAnalyzer），`classify_sync()` sync 入口（供 Router）。
- 重构 `src/core/router.py`（-130 行）：移除自有 LLM/关键词逻辑和 `_matches_*` 辅助函数，持有 `DomainClassifier`，`route_event()` 委托 `classify_sync()`。
- 重构 `src/retrieval/intent_analyzer.py`（-150 行）：移除 `_KEYWORD_RULES`/`_analyze_with_llm()`/`_keyword_fallback()`，持有 `DomainClassifier`，`analyze()` 委托 `classify()`。
- 移除 `Router.route_query()` 死代码（无调用方）。
- `MemoryService` 创建 `DomainClassifier` 实例并传入 Router 和 IntentAnalyzer，确保同一实例复用。
- 适配测试：`test_router.py` 新增 CLI 关键词路由测试、FakeLLM 改用 `atext()`；`test_service.py` FakeLLM 同时支持 `atext()`（路由）和 `ajson()`（准入/抽取）。
- 验证：`python -m pytest tests -q`，400 passed, 6 subtests passed；`python -m compileall src tests` 通过。

## 2026-05-03 方向 A CLI 工作流记忆 — 完整交付

### 阶段 1：后端 domain 记忆引擎

- 已实现 `src/domains/cli_workflow/` 完整领域（5 个文件）：
  - `models.py`：`CLIWorkflowMemory` 模型 + `ParameterBinding` + `MemoryCore` 双向转换（`to_memory_core` / `from_memory_core`）。user_id/project_id/command_name 编码进 entities，参数绑定编码进 tags（`param:env=prod`），零侵入通用表结构。
  - `extractor.py`：从 shell 事件（`command_finished`）和 OpenClaw 事件（`memory_feedback`）中提取命令模板和参数绑定。支持 `--key=value`、`--key value`、`-k value`、布尔 flag 和位置参数五种形态。过滤策略：跳过 trivial 命令（cd/ls/echo 等）、跳过非已知工具链且无 flag 的命令、跳过单字裸敲命令。
  - `versioning.py`：Shell 同命令重复执行走 reinforce（execution_count++、合并参数频率）；OpenClaw 显式教学可覆盖 shell 统计（supersede）；Shell 不覆盖已有的 OpenClaw 记忆（reinforce 而非覆盖）。
  - `handler.py`：实现 `MemoryDomainHandler` 协议，编排 extract → admission（`is_admissible`）→ version → store 完整链路。
  - `retriever.py`：按 user_id 隔离 + project_id 过滤 + 命令名/关键词匹配，综合执行频率/新鲜度/成功率/项目匹配多维度打分。输出 `CLIWorkflowSearchResult` 可转为 `RankedMemory`、suggestion 或 completion 候选。
- 已在 `src/app/dependencies.py` 注册 `CLIWorkflowDomainHandler`，与 project_decision / team_retention 完全平行。
- 架构文档中标注的 `ranker.py` 和 `workflow_miner.py` 暂未实现：领域内排序逻辑内聚在 retriever 中，工作流序列挖掘按 PRD 列为"不做的事"。

### 阶段 2：CLI 终端客户端工具

- 已实现 `src/sources/cli/` 完整 CLI 工具（6 个文件）：
  - `main.py`：CLI 入口，5 个子命令路由（hook / suggest / complete / completion / ingest）。
  - `hook.py`：安装/卸载 shell 钩子，标记块管理（`# >>>` / `# <<<`）、可逆幂等、bash/zsh 自适应。
  - `ingest.py`：shell hook 捕获命令后构造 `NormalizedEvent` → POST `/api/v1/ingest`，HTTP 失败静默不影响终端。
  - `retrieve.py`：suggest 查询记忆 / complete 补全候选 → POST `/api/v1/retrieve` → 解析 MemoryHit 响应 → 格式化输出。
  - `completion.py`：动态生成 bash/zsh completion script，错误静默不污染终端，注册为默认回退完成器。
  - `_client.py`：公共 HTTP 客户端模块，集中 `get_api_base()`、`post_ingest()`、`post_retrieve()`。
- Shell hook 机制：
  - Bash：`trap '_lark_preexec' DEBUG` + `PROMPT_COMMAND`
  - Zsh：`add-zsh-hook preexec` + `add-zsh-hook precmd`
  - 异步上报（后台进程 `>/dev/null 2>&1`），不阻塞终端
  - 过滤自身命令（`lark-memory*`）、空命令

### 测试覆盖

- `tests/unit/domains/cli_workflow/`：62 tests — 模型双向转换、提取过滤（trivial/known_prefix/flags/shell/openclaw/参数化）、版本覆盖（reinforce/supersede/cross-source）、检索打分（user 隔离/project 过滤/空查询/频率排序）。
- `tests/unit/sources/cli/`：56 tests — hook 安装/卸载/幂等/保留已有内容/替换旧块、事件构造（成功/失败/用户检测/project 推断）、MemoryHit 解析、suggest 格式化、complete 候选生成、completion 脚本（bash/zsh）。

### 审查与修复

- 已完成代码审查，发现 6 个问题并全部修复：
  1. `is_admissible()` 死代码 → handler 中增加准入判断。
  2. 单字裸敲命令未过滤 → extractor 增加 `len(tokens) == 1` 检查。
  3. 参数绑定频率衰减逻辑 → key 改为 `(param_name, param_value)` 元组，不再衰减。
  4. `_get_api_base()` 重复定义 → 提取到公共 `_client.py` 模块。
  5. `_find_existing` 全表扫描 → 改用 `entity_filters` 下推过滤到 SQL。
  6. zsh `compdef -first-` 无效语法 → 改为 `compdef '*'` 标准语法。
- 全量验证：396 passed, 6 subtests passed，零回退。

## 2026-05-03 Core 层统一动态路由（DomainClassifier 重构）

- 新增 `src/core/domain_classifier.py`：统一四域分类器，LLM `atext()` 四标签纯文本（temperature=0）+ 硬规则（`command_finished`→CLI）+ 统一关键词降级。
- 重构 `Router`（-130行）和 `IntentAnalyzer`（-150行）：各自委托 `DomainClassifier`，移除自有 LLM/关键词逻辑。`MemoryService` 创建单一实例同时注入二者。
- 修复双 primary 路径漏了 secondary affinity。
- 新增 28 个 `DomainClassifier` 独立单测。

## 2026-05-03 方向 A — 同事审查第二轮修复

- 移除 Router 中未使用的 `default_domain` 参数（fallback 由 DomainClassifier 统一管理）。
- 根据 classifier 返回值动态设置 `RouteDecision.fallback_used`（method="keyword_rule" 且 confidence≤0.3 时）。
- 新增 `tests/unit/core/test_domain_classifier.py`：28 tests 覆盖四域关键词命中、双 primary、零命中 fallback、memory_feedback 不触发硬规则、LLM 异常降级、_parse_label 非法输入抛异常。

## 2026-05-03 方向 A — 阶段 3：OpenClaw 插件接入

- 插件改为纯管道，不做方向特定逻辑。所有消息统一处理：`source_type` 改为 `"openclaw"`。
- `before_prompt_build`：增加 `ingestEvent(userMessage)` 始终发送用户消息到后端（fire-and-forget），后端 `DomainClassifier` 负责路由到对应 domain。
- `agent_end`：payload 增加 `user_query`，将完整对话上下文（用户问题 + Agent 回复）发给后端。
- `buildMemoryContext`：统一使用 `content_text`（所有 domain），替换仅用 `summary_text` 的旧逻辑。
- 验证：428 passed, 6 subtests passed。

## 2026-05-04 ProjectDecision Embedding 存储

- 已新增 `src/domains/project_decision/embedding.py`，实现 `ProjectDecisionEmbeddingIndexer`：
  - `build_text()` 将主题、结论、完整结论、理由、反对意见、备选方案、阶段、范围和来源组装为稳定语义索引文本。
  - `build_metadata()` 写入 `memory_id`、`domain`、`status`、scope、topic、stage、source_ref，并过滤空值。
  - `upsert()` 复用现有 `EmbeddingStore` / `EmbeddingClient`；embedding client 或 store 失败只记录 warning，不阻断 ingest。
- `ProjectDecisionDomainHandler.ingest_event()` 已在新决策成功写入 `MemoryCore` 后写入旁路向量索引；去重命中旧 memory_id 时不会为新 candidate 重复索引。
- `src/app/dependencies.py` 已给 `ProjectDecisionDomainHandler` 注入 `embedding_store` 和 `embedding_client`，与 `team_retention` 的 embedding 装配保持一致。
- 已新增 `tests/unit/domains/project_decision/test_embedding.py` 和 `test_handler.py`，覆盖索引文本、metadata、向量写入、去重跳过索引和索引失败容错。
- 验证：`python -m pytest tests\unit\domains\project_decision -q -p no:cacheprovider`，30 passed。
- 验证：`python -m pytest tests\unit\core\test_service.py tests\unit\app\test_dependencies.py tests\unit\domains\project_decision -q -p no:cacheprovider`，65 passed。
- 验证：`python -m compileall src tests`，通过。

## 2026-05-04 ProjectDecision Embedding 检索接入

- `ProjectDecisionRetriever` 已接入 `EmbeddingStore` / `EmbeddingClient`，保留原规则检索作为兜底，并将向量命中作为额外召回和加分信号。
- 检索流程更新为：先做 project/team/workspace/stage metadata 过滤的向量召回，再从 `MemoryCoreStore` 回表补充候选，最后与原规则候选一起打分排序。
- 向量相似度按 `1 - distance` 归一化，最高贡献 0.35 分；命中会写入 `matched_fields=["vector_similarity"]` 和 `memory_item.extra["vector_similarity"]`，便于 trace/API 层观察。
- 向量检索失败只记录 warning 并返回空向量命中，不影响原 `_load_candidates()`、`_filter_candidates()`、`_score_matches()` 规则链路。
- `ProjectDecisionDomainHandler` 默认创建 retriever 时已透传 embedding 依赖，保证 API/runtime 注入的 embedding 配置能同时用于 ingest 和 retrieve。
- 新增/更新 `tests/unit/domains/project_decision/test_retriever.py`、`test_handler.py`，覆盖向量补充候选、embedding client 查询向量、向量失败规则兜底和 handler 依赖透传。
- 验证：`python -m pytest tests\unit\domains\project_decision tests\unit\app\test_dependencies.py tests\unit\core\test_service.py -q -p no:cacheprovider`，69 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，459 passed, 1 skipped。

## 2026-05-04 Query Variants 并行向量召回

- `RewrittenQuery` 新增 `query_variants`，由 `QueryRewriter` 生成原始 query + LLM rewritten query 的去重列表；纯规则 rewrite 时只保留原始 query。
- `MemoryService.retrieve_async()` 会把 `rewritten_text` 和 `query_variants` 写入传给 domain handler 的 `session_context`，不改变外部 API schema，也不影响规则检索默认输入。
- `ProjectDecisionQuery.from_retrieval_query()` 已读取 `session_context["query_variants"]`，供领域 retriever 的 embedding 召回使用。
- `ProjectDecisionRetriever._vector_hits()` 改为逐个 query variant 做向量检索，同一 memory 取最高 similarity，并记录命中的 `vector_query`；单个 variant 失败只跳过该路，不阻断其他 variant 和规则兜底。
- 新增测试覆盖 query variants 生成、service 到 handler 的传递、多路向量召回融合、单路失败容错。
- 验证：`python -m pytest tests\unit\domains\project_decision tests\unit\retrieval tests\unit\core\test_service.py tests\unit\app\test_dependencies.py -q -p no:cacheprovider`，85 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，463 passed, 1 skipped。

## 2026-05-04 BM25 关键词检索接入

- `MemoryCoreStore.create_table()` 新增 `memory_core_fts` FTS5 虚拟表，索引 summary、content、tags、entities，并保留 memory_id/domain/status/scope 作为过滤字段。
- `insert_memory_core()`、`update_memory_status()`、`mark_superseded()`、`delete_memory()` 已同步维护 FTS 旁路索引，保证状态过滤和删除结果与主表一致。
- 新增 `MemoryCoreStore.search_bm25()`，使用 FTS5 `bm25()` 排序并返回正向 `bm25_score`；空查询或纯标点查询返回空结果。
- `ProjectDecisionRetriever` 已接入 BM25 关键词召回：先查询 `project_decision` 域 FTS 候选，再与原规则候选和向量候选一起回表、过滤、打分。
- BM25 命中最高贡献 0.3 分，并写入 `matched_fields=["bm25"]` 和 `memory_item.extra["bm25_score"]`；BM25 异常只记录 warning，不阻断规则/向量兜底。
- 新增测试覆盖 BM25 插入检索、domain/status 过滤、状态更新、删除同步、空查询容错和 project_decision BM25 加分。
- 验证：`python -m pytest tests\unit\storage tests\unit\domains\project_decision tests\unit\retrieval tests\unit\core\test_service.py tests\unit\app\test_dependencies.py -q -p no:cacheprovider`，120 passed, 1 skipped。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，467 passed, 1 skipped。

## 2026-05-04 ProjectDecision RRF 与 Rerank 重排

- `ProjectDecisionRetriever` 主检索链路改为 BM25 recall、embedding recall、rule fallback recall 三路结构，再用 RRF 融合候选池。
- 当 BM25 或 embedding 有命中时，规则检索不参与主召回；当两者都无命中时，规则检索作为 fallback 进入 RRF。
- 新增 `ProjectDecisionRecallHit`，保留每路召回的 source、rank、score 和 metadata；融合后写入 `recall_sources`、`rrf_score`、`bm25_score`、`vector_similarity` 等可观测字段。
- `ProjectDecisionRetriever` 新增可选 `rerank_client`，对 RRF 候选池调用 rerank 模型重排；rerank 不可用或失败时回退 RRF 顺序。
- `ProjectDecisionDomainHandler` 和 `src/app/dependencies.py` 已透传 `get_rerank_client()`，使配置启用的 rerank 服务进入 project_decision 检索链路。
- 保留 core 层跨 domain `Reranker`，domain 内排序先由 RRF/rerank 决定，再交给 core 层做跨域融合。
- 新增测试覆盖 BM25/vector RRF 融合、规则 fallback、rerank 模型重排、rerank 失败回退和依赖注入。
- 验证：`python -m pytest tests\unit\domains\project_decision tests\unit\app\test_dependencies.py tests\unit\core\test_service.py tests\unit\retrieval tests\unit\storage -q -p no:cacheprovider`，125 passed, 1 skipped。

## 2026-05-04 阶段 13：Source 层基础设施

- 已新增 `src/storage/source_state_store.py` — Source 层轻量处理状态 DB：
  - 复用 `SQLiteStore` 基类，独立 DB 文件 `.larkmemory/source_state.db`，与 backend 记忆引擎 DB 物理隔离。
  - 表 `source_processed(source_type, external_id, status, last_hash, cursor_value, metadata_json, processed_at, error_count)`。
  - 提供 `upsert_state`（幂等写入/更新）、`get_state`、`list_pending`（按 oldest first）、`list_by_status`、`mark_complete`、`mark_error`（累加 error_count）、`update_cursor`、`update_hash`、`delete_states_before`。
  - `upsert_state` 使用 `ON CONFLICT DO UPDATE` 实现幂等，`COALESCE` 保证 hash/cursor 在显式传 None 时保留旧值。
- 已新增 `src/sources/_shared/chunker.py` — 通用文本切分工具：
  - `split_by_headings(markdown_text)` 按 Markdown H1/H2 标题切分，支持 preamble（标题前导文）、H3 忽略、chunk_id 唯一性。
  - `split_by_chapters(verbatim_text, chapters)` 按妙记 AI 章段时间戳切分逐字稿，支持无时间戳行跟随前一章节、空章节跳过、尾部内容处理。
  - `ChunkResult` 包含 `chunk_id`、`content`、`heading`、`heading_level`、`index`、`metadata`。
- 已在 `src/storage/__init__.py` 导出 `SourceStateStore`，与 `EventStore`、`MemoryCoreStore` 平级。
- 组织原则：持久化逻辑归入 storage 层，纯文本处理归入 sources/_shared/，两层通过依赖注入协作。
- 已更新 `memory-bank/architecture.md`：Source Adapter 层文件树增加 `_shared/chunker.py`、calendar/task/meeting/doc 事件模块、scanner 目录；补充"多信息源扩展模式"章节（类型 A: 1:1 映射 / 类型 B: 多步骤+1:N 切分）。
- 已更新 `memory-bank/implementation-plan.md`：新增阶段 13（Source 层基础设施）、14（日历接入）、15（任务接入）、16（妙记接入）、17（文档接入）。
- 新增测试：
  - `tests/unit/storage/test_source_state_store.py`：16 tests — CRUD、幂等 upsert、COALESCE 保留旧值、metadata 存取、多状态过滤、limit、排序、多 source_type 隔离、error_count 累加、delete 清理。
  - `tests/unit/sources/_shared/test_chunker.py`：19 tests — 空文本、无标题全文、H1/H2 单标题、preamble、多标题混合、H3 忽略、特殊字符标题、空章节跳过、时间戳边界切分、无时间戳行跟随、尾部内容、chunk_id 唯一性。
- 验证：`python -m pytest tests/unit/storage/test_source_state_store.py tests/unit/sources/_shared/test_chunker.py -q -p no:cacheprovider`，35 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q -p no:cacheprovider`，499 passed, 6 subtests passed。

## 2026-05-04 阶段 13 审查修复

- 修复 `SourceStateStore` 6 处局部 `from src.utils.time import utc_now_iso` → 提升到模块顶部统一导入。
- 修复 `split_by_chapters` 不可达 `tail_bucket` 死代码：while 循环 `current_chapter_idx + 1 < len(chapter_boundaries)` 严格保证 `current_chapter_idx < len(chapter_buckets)` 恒真，删除 else 分支和尾部处理块。
- 新增 `SourceStateStore.reset_error()` 方法，显式重置 `error_count` 为 0。
- `upsert_state` 写入新行时显式设置 `error_count = 0`，ON CONFLICT 更新时也重置为 0，确保错误修复后重新 upsert 不会残留旧计数值。
- 补充 COALESCE 语义边界测试：`test_upsert_empty_string_overwrites_hash`（空字符串覆盖旧值）、`test_upsert_none_preserves_hash`（None 保留旧值）、`test_upsert_resets_error_count`、`test_reset_error`。
- 补充 `test_content_beyond_last_boundary_stays_in_last_chapter`：超出最后章节边界的行归入最后一章而非独立尾部。
- 验证：`python -m pytest tests/unit/storage/test_source_state_store.py tests/unit/sources/_shared/test_chunker.py -q`，39 passed。
- 验证：`python -m pytest tests -q`，503 passed, 6 subtests passed，零回退。

## 2026-05-04 阶段 14：飞书日历接入

- 已新增 `src/sources/feishu/events/calendar_models.py` — `FeishuCalendarEvent` 模型：
  - 字段：`calendar_event_id`、`summary`、`description`、`start_time`、`end_time`、`organizer_id`、`attendee_ids`、`location`、`recurrence`、`status`、`raw_payload`。
- 已新增 `src/sources/feishu/events/calendar_normalizer.py` — 1:1 映射：
  - `calendar_event_to_normalized_event()` → `NormalizedEvent(event_type="calendar_event", source_type="feishu_calendar")`。
  - `summary` + `description` 合并为 `content_text`，结构化字段（时间/地点/参会人/重复规则）存入 `payload`。
  - tags 包含 `calendar`、`feishu`、status 和可选的 `recurring`。
- 已扩展 `src/sources/feishu/client/listener.py`：
  - 新增 `on_calendar_event()` 回调：`_calendar_event_from_lark()` 提取 → normalizer → dispatcher。
  - 新增 `_calendar_event_from_lark()` 提取函数：从 lark-oapi 回调对象中提取日历字段（含 attendees 列表展开、organizer id、status 空值兜底）。
  - 新增 `_attr_str()` 辅助方法，安全转换 SDK 属性为 `str | None`。
  - `build_event_handler()` 注册 `register_p2_calendar_event_changed_v4(on_calendar_event)`。
- 已更新 `tests/unit/sources/feishu/test_listener.py`：
  - `_FakeBuiltHandler` 新增 `calendar_handler` 和 `register_p2_calendar_event_changed_v4()`。
  - 现有 `test_build_event_handler` 断言增加 `calendar_handler is not None`。
- 新增测试 `tests/unit/sources/feishu/test_calendar_events.py`：13 tests：
  - `TestCalendarNormalizer`：基本字段映射、payload 结构化、空描述、tentative/cancelled/recurring 状态。
  - `TestCalendarEventDispatch`：通过 dispatcher 存入 event_store、触发 project_decision 抽取、重复事件容忍。
  - `TestCalendarEventFromLark`：从 SimpleNamespace 提取字段、无事件/无 ID 返回 None、空 attendees、无 organizer_id。
- 特点：事件驱动 + 1:1 映射，不需要 source_state_store 或 chunker，完全复用现有 dispatcher 模式。
- 验证：`python -m pytest tests/unit/sources/feishu/test_calendar_events.py tests/unit/sources/feishu/test_listener.py -q`，16 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q`，516 passed, 6 subtests passed。

## 2026-05-04 阶段 14 审查修复

- 修复 `_attr_str` 无法提取 lark-oapi 嵌套对象字段：新增 `_nested_attr_str(obj, outer, inner)` 函数，对 `start_time`/`end_time` 深入取 `date_time`，对 `location` 深入取 `name`，避免 `str(TimeInfo)` 把整个对象序列化为 Python repr。
- 修复 `schemas/event.py` Literal 类型缺失：`EventType` 新增 `"calendar_event"`，`SourceType` 新增 `"feishu_calendar"`，确保下游 router、domain handler 等依赖 Literal 分发时不会静默漏掉日历事件。
- 修复 `calendar_normalizer` 的 `occurred_at` 语义：优先使用 `event.start_time`（事件实际发生时间），`None` 时 fallback 到 `utc_now_iso()`，与 IM normalizer 使用消息 `create_time` 的模式保持一致，避免飞书重试推送时 `occurred_at` 次次不同。
- 测试补强：`test_extracts_basic_fields` 补充 `start_time`/`end_time`/`location`/`recurrence`/`status` 断言；新增 `test_nested_fields_none_when_outer_is_none` 和 `test_nested_fields_none_when_inner_is_none` 覆盖嵌套对象为 None 的降级路径；新增 `test_normalizer_falls_back_occurred_at_when_no_start_time` 覆盖 occurred_at 降级。
- 验证：`python -m pytest tests/unit/sources/feishu/test_calendar_events.py tests/unit/sources/feishu/test_listener.py -q`，19 passed。
- 验证：`python -m pytest tests -q`，519 passed, 6 subtests passed，零回退。

## 2026-05-04 阶段 15：飞书任务接入

- 已新增 `src/sources/feishu/events/task_models.py` — `FeishuTaskEvent` 模型：
  - 字段：`task_id`、`task_name`、`description`、`status`、`start_time`、`due_time`、`creator_id`、`assignee_ids`、`follower_ids`、`tasklist_name`、`priority`、`url`、`raw_payload`。
- 已新增 `src/sources/feishu/events/task_normalizer.py` — 1:1 映射：
  - `task_event_to_normalized_event()` → `NormalizedEvent(source_type="feishu_task")`。
  - event_type 按 status 区分：`"task_created"`（pending）、`"task_completed"`（completed）、`"task_updated"`（其他/空）。
  - `task_name` + `description` 合并为 `content_text`，全部结构化字段（含 assignees/followers/tasklist/priority/url）存入 `payload`。
  - `occurred_at` 优先 `start_time`，其次 `due_time`，最后 fallback `utc_now_iso()`。
  - tags 包含 `task`、`feishu`、status 和 priority。
- 已扩展 `src/schemas/event.py`：`EventType` 新增 `"task_created"`/`"task_updated"`/`"task_completed"`，`SourceType` 新增 `"feishu_task"`。
- 已扩展 `src/sources/feishu/client/listener.py`：
  - 新增 `on_task_event()` 回调：`_task_event_from_lark()` 提取 → normalizer → dispatcher。
  - 新增 `_task_event_from_lark()` 提取函数：从 lark-oapi 回调对象提取任务字段（含 `name`/`summary` fallback、assignees/followers 列表展开、tasklist.name 嵌套提取、creator.id 提取）。
  - `build_event_handler()` 注册 `register_p2_task_updated_v2(on_task_event)`。
- 新增测试 `tests/unit/sources/feishu/test_task_events.py`：16 tests：
  - `TestTaskNormalizer`：基本字段映射、completed/pending/empty status、payload 结构化、occurred_at 三层降级、空描述。
  - `TestTaskEventDispatch`：dispatcher 存入 event_store、触发 team_retention 抽取、重复事件容忍。
  - `TestTaskEventFromLark`：SimpleNamespace 提取（含 name/summary fallback、assignees/followers/tasklist 嵌套）、空列表、嵌套字段 None。
- 已更新 `tests/unit/sources/feishu/test_listener.py`：`_FakeBuiltHandler` 新增 `task_handler` 和 `register_p2_task_updated_v2()`，现有测试断言 task_handler 非空。
- 特点：与日历同属"类型 A"（事件驱动 + 1:1 映射），不需要 source_state_store 或 chunker，payload 结构化字段可直接供 team_retention domain handler 使用。
- 验证：`python -m pytest tests/unit/sources/feishu/test_task_events.py tests/unit/sources/feishu/test_listener.py tests/unit/sources/feishu/test_calendar_events.py -q`，35 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q`，535 passed, 6 subtests passed。

## 2026-05-04 阶段 16a：飞书妙记接入（核心链路）

- 已新增 `src/sources/feishu/client/vc_client.py` — 飞书 VC API 客户端：
  - `FeishuVcClientProtocol` 定义 `get_recording(meeting_id)→str` 和 `get_notes(minute_token)→MeetingNotesData` 接口。
  - `FeishuVcClient` 实现：调用 `vc/v1/meetings/{id}/recording` 获取 `minute_token`，调用 `vc/v1/minutes/{token}/notes` 获取 AI 产物（summary/todo_list/chapter_list/transcript），todo_list 含 assignees 列表展开和 due_time 时间戳转换。
- 已新增 `src/sources/feishu/events/meeting_models.py`：
  - `FeishuMeetingEndedEvent`（meeting_id/topic/start_time/end_time/organizer_id/participant_ids）。
  - `MeetingNotesData`（summary/todos:MeetingTodo/chapters:MeetingChapter/verbatim_text/minute_token）。
  - `MeetingTodo`（title/content/due_time/assignee_ids）、`MeetingChapter`（title/start_time_ms）。
- 已新增 `src/sources/feishu/events/meeting_normalizer.py` — 四个 normalizer 函数：
  - `meeting_ended_to_event()` → `event_type="meeting_summary"`（会议结束事件本身，不依赖 AI 产物）。
  - `meeting_summary_to_event()` → `event_type="meeting_summary"`（AI 总结锚点事件）。
  - `meeting_todo_to_event()` → `event_type="meeting_todo"`（单条待办，含 due_time/assignees）。
  - `meeting_chapter_to_event()` → `event_type="meeting_chapter"`（单个章节的逐字稿片段）。
- 已新增 `src/sources/feishu/events/meeting_processor.py` — 多步骤编排：
  - `MeetingProcessor` 依赖 `SourceStateStore` + `FeishuVcClientProtocol` + `FeishuEventDispatcher`。
  - `process_meeting_ended_async()` 在 daemon 线程中异步处理，不阻塞 WebSocket 回调（3s 内返回 ack）。
  - `_process()` 完整链路：幂等检查→`get_recording` 获取 minute_token→upsert status=pending_ai→等 5min→`get_notes` 拉取 AI 产物（最多重试 5 次，间隔 2min）→`chunker.split_by_chapters` 切分→批量 `dispatch_normalized_event`→`mark_complete`。
  - 异常时 `mark_error`，AI 产物未就绪时保持 `pending_ai` 由 scanner（16b）兜底。
- 已扩展 `src/schemas/event.py`：`EventType` 新增 `"meeting_chapter"`/`"meeting_summary"`/`"meeting_todo"`，`SourceType` 新增 `"feishu_vc"`。
- 已扩展 `src/sources/feishu/client/listener.py`：
  - `build_event_handler()` 新增可选参数 `source_state_store` 和 `vc_client`，两者均提供时创建 `MeetingProcessor` 并注册 `vc.meeting.ended_v1` 事件。
  - `on_meeting_ended` 回调：先 dispatch meeting_ended 事件（不依赖 AI），再异步启动 processor 处理妙记产物。
  - 新增 `_meeting_ended_from_lark()` 提取函数和 `_nested_attr_str()` 辅助函数。
- 新增测试 `tests/unit/sources/feishu/test_meeting_events.py`：15 tests：
  - `TestMeetingNormalizer`：4 个 normalizer 函数映射、occurred_at 降级、todo 空标题 fallback。
  - `TestMeetingProcessor`：完整链路（mock vc_client + 归零延迟常量）、幂等跳过已 complete 会议、事件数量验证（summary+todo+chapter）。
  - `TestMeetingEventFromLark`：SimpleNamespace 提取、topic/name fallback、空事件/无 meeting_id。
  - `TestMeetingChapterChunking`：chunker 与 normalizer 集成。
- 已更新 `tests/unit/sources/feishu/test_listener.py`：`_FakeBuiltHandler` 新增 `meeting_handler` 和 `register_p2_vc_meeting_ended_v1()`。
- 验证：`python -m pytest tests/unit/sources/feishu/test_meeting_events.py tests/unit/sources/feishu/test_listener.py -q`，18 passed。
- 验证：`python -m compileall src tests`，通过。
- 验证：`python -m pytest tests -q`，550 passed, 6 subtests passed。

## 2026-05-04 阶段 16b：妙记 Scanner 兜底

- 已新增 `src/sources/feishu/scanner/meeting_scanner.py` — 定时扫描兜底：
  - `MeetingScanner` 依赖 `SourceStateStore` + `FeishuVcClientProtocol` + `FeishuEventDispatcher`。
  - `run()` 扫描 `source_state_store.list_pending("feishu_vc")`，过滤 `error_count > 10` 的死信。
  - 对每条待处理记录：检查 `minute_token` 是否存在→调用 `vc_client.get_notes()`→产物就绪则 chunker 切分+批量 dispatch+mark_complete，仍未就绪则 mark_error 累加 error_count。
  - 返回本次成功补处理的数量，供调度方监控。
- 修复 `SourceStateStore.list_pending()` 的 WHERE 子句：`status IN ('pending', 'partial', 'error')` → `status IN ('pending', 'pending_ai', 'partial', 'error')`，补上 processor 写入的 `pending_ai` 状态。
- 新增测试 `tests/unit/sources/feishu/test_meeting_scanner.py`：6 tests：
  - 成功补处理 pending_ai 记录、跳过已 complete、跳过死信（error_count>10）、产物仍空时 mark_error、无 minute_token 时 mark_error、事件 dispatch 验证。
- 验证：`python -m pytest tests/unit/sources/feishu/test_meeting_scanner.py -q`，6 passed。
- 验证：`python -m pytest tests -q`，556 passed, 6 subtests passed。
