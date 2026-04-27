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
- `python -m pytest tests -q -p no:cacheprovider`：177 passed, 6 subtests passed。
- HTTP 手工验证：`/health`、`/api/v1/ingest`、`/api/v1/retrieve` 通过。
- 插件轻量验证：`openclaw.plugin.json` 可解析；旧 `before_agent_reply` 和 mock 后端调用无残留。

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
