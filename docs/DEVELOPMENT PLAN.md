# Python Memory Engine 开发计划简版

## 1. 定位

方案采用 `OpenClaw 插件（TypeScript） + 本地 Python Memory Engine 服务`。

- 插件负责采集上下文、发起请求、注入记忆结果。
- Python 服务负责长期记忆的抽取、存储、检索和更新。
- 服务默认运行在 `localhost`，由插件按需探测和拉起。

---

## 2. Python 文件一句话说明

### `app/`

- `main.py`：FastAPI 服务入口，负责启动应用并注册所有接口。
- `config.py`：集中管理端口、路径、模型参数和运行开关。
- `dependencies.py`：为 API 层统一提供 service、store 等依赖对象。
- `logging.py`：初始化结构化日志与请求链路日志能力。

### `api/`

- `ingest.py`：接收外部事件并触发记忆写入流程。
- `retrieve.py`：接收检索请求并返回相关记忆结果。
- `update.py`：处理记忆纠正、覆盖和失效标记。
- `proactive.py`：提供提醒、建议和复习类主动结果。
- `benchmark.py`：暴露评测运行与结果查询接口。
- `health.py`：提供服务健康检查和依赖状态检查。

### `core/`

- `router.py`：根据事件或查询意图把请求路由到合适的领域模块。
- `memory_core.py`：定义统一记忆对象及其状态流转规则。
- `admission_control.py`：决定哪些候选信息值得进入长期记忆。
- `dedup_merge.py`：识别重复内容并合并相近记忆。
- `supersede.py`：管理新旧记忆的覆盖关系和版本链。
- `decay.py`：负责记忆衰减、归档和遗忘策略。
- `access_tracker.py`：记录命中、采纳和反馈以反向优化排序。
- `scheduler.py`：调度复习、提醒和过期扫描等后台任务。
- `service.py`：作为后端统一业务入口串联各层能力。

### `domains/cli_workflow/`

- `models.py`：定义 CLI 工作流相关的结构化数据模型。
- `extractor.py`：从命令和执行上下文中抽取工作流记忆。
- `retriever.py`：按 repo、任务和命令语境检索 CLI 记忆。
- `ranker.py`：对 CLI 记忆结果做领域内排序。
- `workflow_miner.py`：从命令序列中识别稳定的多步工作流模式。

### `domains/project_decision/`

- `models.py`：定义项目决策、理由和备选方案的数据结构。
- `extractor.py`：从讨论或记录中抽取项目决策信息。
- `retriever.py`：按项目、主题和阶段检索决策记忆。
- `ranker.py`：对决策类结果按相关性和时效性排序。
- `versioning.py`：维护决策更新时的新旧版本关系。

### `domains/personal_preference/`

- `models.py`：定义个人偏好和习惯相关的数据模型。
- `extractor.py`：从用户行为和表达中抽取偏好信息。
- `retriever.py`：按用户、场景和时间模式检索偏好记忆。
- `ranker.py`：对偏好类结果做个性化排序。
- `pattern_miner.py`：分析重复行为并挖掘稳定偏好模式。

### `domains/team_retention/`

- `models.py`：定义团队事实、风险和复习计划的数据模型。
- `extractor.py`：从协作信息中抽取团队关键事实。
- `retriever.py`：按团队、项目和风险维度检索团队记忆。
- `ranker.py`：对团队记忆结果按重要性和风险等级排序。
- `review_planner.py`：生成团队知识复习和提醒计划。
- `versioning.py`：维护团队事实的生效、失效和替换关系。

### `storage/`

- `event_store.py`：存储原始事件，便于回放、调试和评测。
- `memory_core_store.py`：负责统一记忆主表的读写操作。
- `cli_workflow_store.py`：负责 CLI 工作流记忆的存储与检索。
- `project_decision_store.py`：负责项目决策记忆的存储与检索。
- `personal_preference_store.py`：负责个人偏好记忆的存储与检索。
- `team_retention_store.py`：负责团队事实记忆的存储与检索。
- `embedding_store.py`：提供向量索引和语义检索能力。
- `review_schedule_store.py`：存储复习计划和下次提醒时间。
- `access_log_store.py`：记录检索命中、采纳和反馈日志。

### `retrieval/`

- `intent_analyzer.py`：分析查询意图并决定主查与辅查领域。
- `query_rewrite.py`：补全主题、时间和上下文等检索信号。
- `fusion.py`：融合多个领域的召回结果。
- `rerank.py`：对跨领域结果做统一重排。
- `retrieval_trace.py`：记录完整检索链路用于调试和评测。

### `llm/`

- `client.py`：封装大模型调用并输出结构化结果。
- `prompts.py`：集中管理通用提示词模板。
- `extraction_prompts.py`：维护抽取类任务使用的提示词。
- `decision_prompts.py`：维护决策类任务使用的提示词。

### `jobs/`

- `review_scan.py`：扫描需要复习或提醒的记忆项。
- `decay_compaction.py`：处理低活跃记忆的衰减、归档和压缩。
- `benchmark_runner.py`：统一执行基准评测任务。

### `schemas/`

- `event.py`：定义事件输入输出的数据结构。
- `memory_core.py`：定义统一记忆对象的协议模型。
- `ingest.py`：定义写入接口的请求和响应模型。
- `retrieve.py`：定义检索接口的请求和响应模型。
- `update.py`：定义更新接口的请求和响应模型。
- `proactive.py`：定义主动提醒接口的请求和响应模型。
- `benchmark.py`：定义评测接口的请求和响应模型。

### `utils/`

- `ids.py`：提供统一 ID 生成与解析工具。
- `time.py`：提供时间处理、格式化和窗口计算工具。
- `text.py`：提供文本清洗、截断和规范化工具。
- `jsonlog.py`：提供 JSON 日志输出辅助方法。

---

## 3. 核心 API

- `POST /ingest`：接收标准化事件并写入记忆。
- `POST /retrieve`：根据当前问题和上下文召回相关记忆。
- `POST /update`：处理记忆纠正、覆盖和失效。
- `GET /proactive`：返回当前应主动提醒或推荐的内容。
- `POST /benchmark/run`：执行指定评测任务。
- `GET /health`：检查服务和依赖是否正常。

---

## 4. 建议开发顺序

### 第一批

- `app/main.py`
- `api/ingest.py`
- `api/retrieve.py`
- `api/health.py`
- `core/service.py`
- `core/router.py`
- `core/memory_core.py`
- `storage/event_store.py`
- `storage/memory_core_store.py`
- `domains/cli_workflow/extractor.py`
- `domains/cli_workflow/retriever.py`

### 第二批

- `domains/project_decision/*`
- `retrieval/intent_analyzer.py`
- `retrieval/fusion.py`
- `api/update.py`

### 第三批

- `domains/team_retention/*`
- `domains/personal_preference/*`
- `jobs/review_scan.py`
- `api/proactive.py`
- `api/benchmark.py`

---

## 5. 结论

当前最合适的落地方式是保留 TypeScript 插件层，并用 Python 实现本地记忆引擎服务，以兼顾开发效率、建模能力和后续扩展性。
