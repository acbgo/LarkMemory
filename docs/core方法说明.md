# core 模块方法说明

本文档介绍 `src/core` 目录下每个 Python 文件、类、函数和方法的职责。该目录是 Memory Engine 的核心编排层，负责准入、路由、去重合并、生命周期、衰减、访问记录、调度、替换关系和统一服务封装。

## 目录总览

- `__init__.py`：统一导出 core 包的主要组件。
- `access_tracker.py`：记录记忆访问和反馈，并提供最近访问统计。
- `admission_control.py`：判断事件或记忆是否应进入 MemoryCore。
- `decay.py`：计算记忆新鲜度，并按 domain 策略过期记忆。
- `dedup_merge.py`：检测重复记忆，必要时合并候选记忆与已有记忆。
- `memory_core.py`：提供记忆生命周期状态机和 MemoryCore 创建工具。
- `router.py`：按事件或查询内容路由到记忆 domain。
- `scheduler.py`：运行维护任务，目前包括衰减扫描和 review 占位扫描。
- `service.py`：聚合 store、retrieval、准入、去重、替换和维护能力，提供同步服务 API。
- `supersede.py`：检测和维护记忆替换关系。

## `__init__.py`

### 文件职责

该文件是 `src.core` 包的公共入口，导出核心组件类。

### 导出内容

- `AccessTracker`
- `AdmissionController`
- `DecayPolicy`
- `DedupMergeEngine`
- `DomainRouter`
- `MemoryLifecycle`
- `MemoryService`
- `Scheduler`
- `SupersedeManager`

## `access_tracker.py`

### 文件职责

该文件记录记忆被检索、使用或反馈的访问事件。记录会保存在内存最近队列中，也可通过 `persist_fn` 持久化。

### `AccessRecord`

访问记录 dataclass。

主要字段：
- `access_id`：访问记录 ID。
- `memory_id`：被访问的记忆 ID。
- `access_type`：访问类型，例如 `retrieved` 或 `feedback`。
- `query_id`、`agent_session_id`：可选上下文 ID。
- `used_in_response`：是否被用于最终响应。
- `feedback_signal`：反馈信号。
- `accessed_at`：访问时间。
- `metadata`：额外元数据。

### `AccessTracker`

访问记录器。

#### `__init__(self, persist_fn: Callable[[AccessRecord], None] | None = None, max_recent: int = 200) -> None`

初始化访问记录器。

处理逻辑：
1. 保存可选持久化函数 `persist_fn`。
2. 创建最大长度为 `max_recent` 的 `deque` 保存最近访问。

#### `record_access(...) -> AccessRecord`

记录一次记忆访问。

处理流程：
1. 创建 `AccessRecord`。
2. 使用 `new_id("acc")` 生成访问 ID。
3. 使用 `utc_now_iso()` 记录访问时间。
4. 将记录追加到最近队列。
5. 如果配置了 `persist_fn`，调用它持久化记录。
6. 如果持久化失败，记录 warning，但不影响主流程。
7. 返回访问记录。

#### `record_feedback(...) -> AccessRecord`

记录一次反馈事件。

处理逻辑：转调用 `record_access`，固定 `access_type="feedback"`，并传入 `feedback_signal`、`query_id` 和 metadata。

#### `recent_records(self) -> list[AccessRecord]`

返回最近访问记录的列表拷贝，避免调用方直接修改内部 `deque`。

#### `stats_by_memory(self) -> dict[str, dict[str, int]]`

按 `memory_id` 汇总最近访问统计。

处理逻辑：
1. 遍历 `_recent`。
2. 以 `memory_id` 分组。
3. 对每个 `access_type` 累加计数。
4. 返回嵌套字典。

## `admission_control.py`

### 文件职责

该文件负责准入判断。它根据事件内容、事件类型、记忆重要性和置信度决定是否接纳，以及以 active 还是 candidate 状态进入系统。

### `AdmissionDecision`

准入决策 dataclass。

主要字段：
- `admitted`：是否接纳。
- `status`：建议状态，默认 `candidate`。
- `importance`、`confidence`：建议重要性和置信度。
- `reason`：决策原因。
- `tags`：附加标签。
- `metadata`：附加元数据。

### `AdmissionController`

准入控制器。

#### `__init__(...) -> None`

初始化准入阈值。

参数含义：
- `min_content_length`：普通文本事件的最小长度。
- `direct_admit_importance`：记忆直接进入 active 的重要性阈值。
- `candidate_confidence_threshold`：低于该置信度时保持 candidate。

#### `evaluate_event(self, event: NormalizedEvent, *, domain: str | None = None) -> AdmissionDecision`

评估事件是否值得进入记忆系统。

处理流程：
1. 清洗 `event.content_text` 或 `event.title`。
2. 判断事件是否携带 `payload` 或 `raw_payload`。
3. `memory_feedback` 事件直接接纳为 active。
4. 文本和 payload 都为空时拒绝。
5. 命令完成/失败事件如果带 payload，接纳为 candidate。
6. 如果文本中含决策、必须、截止、风险、偏好等强记忆信号，接纳为 active。
7. 文本过短且没有 payload 时拒绝。
8. 其他有效事件接纳为 candidate。

#### `evaluate_memory(self, memory: MemoryCore) -> AdmissionDecision`

评估一条 MemoryCore 是否可写入。

处理流程：
1. 如果 `content_text` 清洗后为空，拒绝。
2. 如果 `importance` 达到直接准入阈值且 `confidence` 达到候选置信度阈值，接纳为 active。
3. 如果 `confidence` 低于候选阈值，接纳但保持 candidate。
4. 其他情况按记忆自身 `status` 接纳。

#### `should_promote(decision: AdmissionDecision) -> bool`

判断准入决策是否意味着应该提升为 active。

返回条件：`decision.admitted` 为真且 `decision.status == "active"`。

## `decay.py`

### 文件职责

该文件负责记忆新鲜度衰减和自动过期。不同 domain 有不同半衰期，部分 domain 有自动过期时间。

### `DecayDecision`

衰减决策 dataclass。

主要字段：
- `memory_id`：目标记忆 ID。
- `new_status`：需要更新的新状态，可能为空。
- `freshness_score`：计算得到的新鲜度。
- `should_update`：是否有更新动作或计算结果。
- `reason`：决策原因。

### `DecayPolicy`

记忆衰减策略。

#### `__init__(...) -> None`

初始化 domain 级衰减参数。

默认半衰期：
- `cli_workflow`：30 天。
- `project_decision`：180 天。
- `personal_preference`：90 天。
- `team_retention`：365 天。

默认过期规则：
- `cli_workflow`：180 天后过期。

调用方可以通过参数覆盖或扩展这些配置。

#### `freshness(self, updated_at: str | None, *, domain: str, now: str | None = None) -> float`

计算记忆新鲜度分数。

处理逻辑：
1. 如果没有更新时间，返回默认 `0.3`。
2. 使用 `now` 或当前 UTC 时间作为当前时间。
3. 调用 `days_between` 计算记忆年龄天数。
4. 按 domain 获取半衰期，缺省为 180 天。
5. 半衰期小于等于 0 时返回 `0.0`。
6. 用指数衰减公式计算分数，并限制在 `[0.0, 1.0]`。

#### `evaluate(self, memory: MemoryCore | dict[str, Any], *, now: str | None = None) -> DecayDecision`

评估单条记忆是否需要衰减或过期。

处理流程：
1. 调用 `memory_from_row` 将 dict 或 MemoryCore 统一为 MemoryCore。
2. 如果状态是 `expired` 或 `forgotten`，返回 terminal status，不再处理。
3. 使用 `updated_at`，没有则使用 `created_at`。
4. 调用 `freshness` 计算新鲜度。
5. 如果该 domain 配置了 `expire_after` 且年龄超过阈值，返回 `new_status="expired"`。
6. 否则返回仅计算新鲜度的决策。

#### `apply(self, memory_store: MemoryCoreStore, memory: MemoryCore | dict[str, Any], *, now: str | None = None) -> DecayDecision`

执行衰减决策。

处理逻辑：
1. 调用 `evaluate`。
2. 如果决策包含 `new_status`，调用 `memory_store.update_memory_status` 更新状态。
3. 返回决策。

## `dedup_merge.py`

### 文件职责

该文件用于检测候选记忆与已有记忆之间的重复或可合并关系，并提供合并策略。

### `DedupResult`

去重结果 dataclass。

主要字段：
- `duplicate_found`：是否命中重复。
- `matched_memory_id`：匹配到的已有记忆 ID。
- `score`：相似度分数。
- `reason`：原因。
- `merged_memory`：达到合并阈值时生成的合并后记忆。

### `memory_from_row(row: MemoryCore | dict[str, Any]) -> MemoryCore`

将 store 行或 MemoryCore 对象统一转换为 `MemoryCore`。

处理逻辑：
1. 如果输入已经是 `MemoryCore`，直接返回。
2. 将 dict 复制一份。
3. 兼容 `entities_json` 和 `tags_json` 字段，转为 `entities` 和 `tags`。
4. 只保留 `MemoryCore` dataclass 定义的字段。
5. 构造并返回 `MemoryCore`。

### `DedupMergeEngine`

去重合并引擎。

#### `__init__(self, duplicate_threshold: float = 0.9, merge_threshold: float = 0.75) -> None`

初始化重复阈值和合并阈值。

#### `similarity(self, left: str, right: str) -> float`

计算两段文本相似度。

处理逻辑：
1. 清洗并小写化两段文本。
2. 任一文本为空时返回 `0.0`。
3. 完全相等时返回 `1.0`。
4. 先提取英文/数字 token 集合。
5. 如果 token 集合为空，退回到字符 bigram 集合。
6. 如果仍无法得到集合，返回 `0.0`。
7. 返回 Jaccard 相似度：交集大小 / 并集大小。

#### `find_duplicate(self, candidate: MemoryCore, existing: list[MemoryCore | dict[str, Any]]) -> DedupResult`

在已有记忆中查找候选记忆的重复项。

处理流程：
1. 遍历已有记忆。
2. 只比较相同 `domain` 和 `scope` 的记忆。
3. 跳过 `expired` 和 `forgotten` 状态。
4. 调用 `similarity` 计算文本相似度。
5. 记录最高分及其对应记忆。
6. 没有可比较记忆时返回 `no comparable memory`。
7. 分数达到 `duplicate_threshold` 时返回重复命中。
8. 分数达到 `merge_threshold` 但未达到重复阈值时，返回可合并结果并附带 `merged_memory`。
9. 否则返回 `no duplicate`。

#### `merge(self, candidate: MemoryCore, existing: MemoryCore | dict[str, Any]) -> MemoryCore`

合并候选记忆和已有记忆。

合并规则：
- 保留已有记忆的 `memory_id`。
- `content_text` 使用更长的一段正文。
- `tags` 和 `entities` 调用 `_merge_list` 去重合并。
- `importance` 和 `confidence` 取两者最大值。
- 如果任一记忆是 active，合并后状态为 active。
- `updated_at` 更新为当前 UTC 时间。

#### `_tokens(text: str) -> set[str]`

提取文本中的英文、数字和下划线 token 集合。

#### `_bigrams(text: str) -> set[str]`

去掉空白后提取字符 bigram 集合。

处理逻辑：对 compact 文本生成所有长度为 2 的连续片段。

#### `_merge_list(left: list[str], right: list[str]) -> list[str]`

按顺序合并两个字符串列表并大小写不敏感去重。

处理逻辑：
1. 先遍历 left，再遍历 right。
2. 以小写值作为去重 key。
3. 保留首次出现的原始写法。

## `memory_core.py`

### 文件职责

该文件定义 MemoryCore 生命周期状态机和创建 MemoryCore 的工具函数。

### `MemoryLifecycle`

记忆生命周期状态机。

#### `can_transition(self, from_status: str, to_status: str) -> bool`

判断状态迁移是否合法。

规则：
- 相同状态迁移只在 `from_status` 是已知状态时允许。
- 不同状态迁移必须出现在 `ALLOWED_STATUS_TRANSITIONS` 中。

#### `validate_transition(self, from_status: str, to_status: str) -> None`

校验状态迁移。

行为：如果 `can_transition` 返回 `False`，抛出 `ValueError`。

#### `transition(self, memory: MemoryCore, to_status: str, *, updated_at: str | None = None) -> MemoryCore`

生成迁移后的 MemoryCore 副本。

处理逻辑：
1. 调用 `validate_transition`。
2. 使用 `dataclasses.replace` 复制原记忆。
3. 更新 `status` 和 `updated_at`。
4. 如果未传 `updated_at`，使用当前 UTC 时间。

### `clamp_score(value: float, *, name: str = "score") -> float`

校验分数字段范围。

行为：
- 值不在 `[0.0, 1.0]` 时抛出 `ValueError`。
- 合法时返回 `float(value)`。

### `create_memory_core(...) -> MemoryCore`

创建一条规范化的 MemoryCore。

处理流程：
1. 调用 `clean_text` 清洗正文。
2. 正文为空时抛出 `ValueError`。
3. 生成当前 UTC 时间。
4. `created_at` 缺省为当前时间。
5. `updated_at` 缺省为 `created_at`。
6. `memory_id` 缺省调用 `src.utils.ids.memory_id()` 生成。
7. `entities` 和 `tags` 缺省为空列表。
8. 调用 `clamp_score` 校验 `importance` 和 `confidence`。
9. 构造并返回 `MemoryCore`。

## `router.py`

### 文件职责

该文件负责把事件或查询路由到合适的记忆 domain。它支持基于 retrieval intent 的查询路由，也支持关键词 fallback。

### `RouteTarget`

路由目标 dataclass。

字段：
- `domain`：目标 domain。
- `priority`：优先级。
- `reason`：命中原因。
- `metadata`：附加元数据。

### `RouteDecision`

路由决策 dataclass。

字段：
- `primary`：主路由目标。
- `secondary`：次级路由目标。
- `fallback_used`：是否使用 fallback。
- `reason`：决策原因。

### `DomainRouter`

domain 路由器。

#### `__init__(self, default_domain: str = "team_retention") -> None`

设置 fallback 默认 domain。

#### `route_event(self, event: NormalizedEvent) -> RouteDecision`

根据事件内容决定写入 domain。

处理流程：
1. 调用 `_event_text` 拼接标题、正文和 payload。
2. 命令完成/失败事件路由到 `cli_workflow`。
3. 命中项目决策关键词时路由到 `project_decision`。
4. 命中偏好关键词时路由到 `personal_preference`。
5. 命中提醒、截止、合规、风险等保留关键词时路由到 `team_retention`。
6. 没有命中时调用 `_fallback`。

#### `route_query(self, query: RetrievalQuery, intent: IntentResult | None = None) -> RouteDecision`

根据查询内容或意图结果决定检索 domain。

处理流程：
1. 如果传入 `intent`，将 `intent.primary_domains` 转成 primary targets，将 `intent.secondary_domains` 转成 secondary targets。
2. 没有 intent 时，按查询文本关键词路由。
3. 命令、构建、部署相关词路由到 `cli_workflow`。
4. 决策相关词路由到 `project_decision`。
5. 偏好相关词路由到 `personal_preference`。
6. 提醒、deadline、risk 等词路由到 `team_retention`。
7. 都不命中时调用 `_fallback`。

#### `get_target_domains(decision: RouteDecision) -> list[str]`

从路由决策中提取去重后的 domain 列表。

处理逻辑：
1. 先遍历 primary，再遍历 secondary。
2. 按出现顺序保留。
3. 已出现的 domain 跳过。

#### `_fallback(self) -> RouteDecision`

生成 fallback 路由。

行为：
- primary 使用 `self.default_domain`。
- secondary 使用 `project_decision`。
- `fallback_used=True`。

#### `_single(domain: str, reason: str) -> RouteDecision`

生成单 domain 路由决策。

行为：创建一个 primary target，并把 `reason` 写入 decision。

#### `_event_text(event: NormalizedEvent) -> str`

拼接事件可检索文本。

内容来源：
- `event.title`
- `event.content_text`
- `event.payload`
- `event.raw_payload`

空值会被跳过。

#### `_matches_project_decision(text: str) -> bool`

判断文本是否命中项目决策类关键词。

命中内容包括决策、方案、选型、架构、why、decision、rationale、choose 等信号词。

## `scheduler.py`

### 文件职责

该文件定义本地维护任务调度器。当前支持衰减扫描，review due 扫描仍是占位。

### `ScheduledTaskResult`

维护任务结果 dataclass。

字段：
- `task_name`：任务名。
- `scanned`：扫描数量。
- `updated`：更新数量。
- `suggestions`：建议列表。
- `errors`：错误列表。

### `Scheduler`

维护任务调度器。

#### `__init__(self, memory_store: MemoryCoreStore, decay_policy: DecayPolicy | None = None) -> None`

初始化调度器。

处理逻辑：
1. 保存 `memory_store`。
2. 如果未传 `decay_policy`，创建默认 `DecayPolicy`。

#### `scan_decay(self, *, domain: str | None = None, limit: int = 500) -> ScheduledTaskResult`

扫描 active 记忆并应用衰减策略。

处理流程：
1. 创建任务名为 `decay` 的结果对象。
2. 调用 `memory_store.list_active_memories(domain=domain, limit=limit)` 获取待扫描记忆。
3. 遍历每条记录并累加 `scanned`。
4. 调用 `decay_policy.apply`。
5. 如果决策包含 `new_status`，累加 `updated`。
6. 单条记录处理异常时捕获异常并写入 `errors`，继续扫描后续记录。
7. 返回任务结果。

#### `scan_review_due(self, *, limit: int = 100) -> ScheduledTaskResult`

review 到期扫描的占位实现。

当前行为：忽略 `limit`，返回任务名为 `review_due` 的空结果。

#### `run_once(self) -> dict[str, ScheduledTaskResult]`

运行一轮维护任务。

处理逻辑：
1. 调用 `scan_decay()`。
2. 调用 `scan_review_due()`。
3. 返回以任务名为 key 的结果字典。

## `service.py`

### 文件职责

该文件提供 `MemoryService`，把 store、准入、路由、去重、检索、更新、访问记录和维护任务聚合成同步服务 API。

### `IngestResult`

事件写入结果 dataclass。

字段包括 `event_id`、`stored`、`memory_ids`、`candidate_count` 和 `message`。

### `RetrieveResult`

检索结果 dataclass。

字段包括 `query_id`、`ranked_memories`、`trace` 和 `message`。

### `UpdateResult`

更新结果 dataclass。

字段包括 `action`、`memory_id`、`updated` 和 `message`。

### `MemoryService`

统一服务门面。

#### `__init__(...) -> None`

初始化 MemoryService 及其依赖。

处理逻辑：
1. 保存必需的 `event_store` 和 `memory_store`。
2. 保存可选的 `embedding_store` 和 `llm_client`。
3. 未传入 router、admission、dedup、supersede、decay_policy、access_tracker 时创建默认实例。
4. `SupersedeManager` 默认绑定当前 `memory_store`。

#### `ingest_event(self, event: NormalizedEvent) -> IngestResult`

写入规范化事件。

处理流程：
1. 调用 `event_store.insert_event(event)` 保存事件。
2. 调用 `router.route_event(event)` 得到路由决策。
3. 取第一个 primary domain 作为准入上下文。
4. 调用 `admission.evaluate_event` 做准入判断。
5. 当前未实现 domain extractor，因此只返回事件已存储，`candidate_count=0`。

#### `add_memory(self, memory: MemoryCore) -> str`

写入一条 MemoryCore。

处理流程：
1. 调用 `admission.evaluate_memory`。
2. 如果不接纳，抛出 `ValueError`。
3. 从 store 中查询同 domain 下 active 和 candidate 记忆作为去重候选。
4. 调用 `dedup.find_duplicate`。
5. 如果命中重复且有 `matched_memory_id`，直接返回已有记忆 ID。
6. 否则调用 `memory_store.insert_memory_core(memory)` 写入并返回新 ID。

#### `retrieve(self, query: RetrievalQuery, *, top_k: int = 10, include_trace: bool = False) -> RetrieveResult`

执行同步检索。

处理流程：
1. 校验 `top_k` 必须大于 0。
2. 生成新的查询 ID。
3. 调用 `IntentAnalyzer.analyze` 分析意图。
4. 调用 `QueryRewriter.rewrite` 改写查询。
5. 从 `memory_store` 拉取 active 记忆，数量为 `max(top_k * 5, 20)`。
6. 将每条 store row 转成 `FusedCandidate`，fusion score 使用 `1.0 / (index + 1)`。
7. 调用 `Reranker.rerank` 得到最终排序。
8. 对每条结果调用 `access_tracker.record_access` 记录访问。
9. 如果 `include_trace` 为真，返回 fallback trace。
10. 返回 `RetrieveResult`。

#### `update_memory(...) -> UpdateResult`

执行记忆更新动作。

支持动作：
- `expire`：要求 `memory_id`，状态更新为 `expired`。
- `forget`：要求 `memory_id`，状态更新为 `forgotten`。
- `supersede`：要求 `memory_id` 和 `new_memory_id`，调用 `supersede.mark_superseded`。
- `confidence`：要求 `memory_id` 和 `confidence`，调用 `update_confidence`。
- `importance`：要求 `memory_id` 和 `importance`，调用 `update_importance`。
- `feedback`：要求 `memory_id` 和 `feedback_signal`，调用 `access_tracker.record_feedback`。

不支持的动作会抛出 `ValueError`。

#### `proactive_suggestions(...) -> list[dict[str, Any]]`

主动建议占位方法。

当前行为：忽略用户、项目、团队和 limit 参数，返回空列表。

#### `run_maintenance(self) -> dict[str, ScheduledTaskResult]`

运行一轮维护任务。

行为：创建 `Scheduler(self.memory_store, self.decay_policy)` 并调用 `run_once()`。

### `_run_async(awaitable: Any) -> Any`

在同步服务 API 中运行异步任务。

处理逻辑：
1. 如果当前没有运行中的事件循环，调用 `asyncio.run(awaitable)`。
2. 如果当前已有事件循环，抛出 `RuntimeError`，提示同步 API 不能在 active event loop 内运行。

## `supersede.py`

### 文件职责

该文件负责检测记忆替换关系，并通过 store 维护版本链。

### `SupersedeDecision`

替换检测结果 dataclass。

字段：
- `should_supersede`：是否应该替换旧记忆。
- `old_memory_id`：被替换的旧记忆 ID。
- `new_memory_id`：新记忆 ID。
- `reason`：原因。
- `confidence`：替换判断置信度。

### `SupersedeManager`

替换关系管理器。

#### `__init__(self, memory_store: MemoryCoreStore) -> None`

保存 `memory_store`，后续标记替换和查询版本链都通过该 store 完成。

#### `detect_conflict(self, candidate: MemoryCore, existing: list[MemoryCore | dict[str, Any]]) -> SupersedeDecision`

检测候选记忆是否替换已有记忆。

处理流程：
1. 遍历已有记忆，并调用 `memory_from_row` 统一类型。
2. 只比较相同 `domain`、`scope` 和 `memory_type` 的记忆。
3. 计算已有记忆与候选记忆的 tags/entities 小写交集。
4. 没有主题重叠时跳过。
5. 如果候选正文含“改为、替换、更新为、change to、replace”等替换信号，则生成替换决策。
6. 如果候选记忆时间晚于已有记忆，置信度提高到 `0.9`，否则为 `0.75`。
7. 遍历结束没有命中时返回 `should_supersede=False`。

#### `mark_superseded(self, old_memory_id: str, new_memory_id: str) -> None`

标记旧记忆被新记忆替换。

行为：直接调用 `memory_store.mark_superseded(old_memory_id, new_memory_id)`。

#### `get_version_chain(self, memory_id: str) -> list[dict[str, Any]]`

查询某条记忆的版本链。

行为：直接调用 `memory_store.get_version_chain(memory_id)`。

#### `_is_later(candidate: MemoryCore, existing: MemoryCore) -> bool`

判断候选记忆是否比已有记忆更新。

处理逻辑：
1. 候选时间优先使用 `valid_from`，否则使用 `created_at`。
2. 已有记忆时间同样优先使用 `valid_from`，否则使用 `created_at`。
3. 两个时间都存在且候选时间字符串更大时返回 `True`。
