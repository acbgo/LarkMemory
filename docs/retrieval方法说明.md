# retrieval 模块方法说明

本文档介绍项目中 `src/retrieval` 目录下每个文件、类、函数和方法的职责。该目录实现记忆检索链路中的意图分析、查询改写、跨域融合、重排和链路追踪能力。

## 目录总览

- `__init__.py`：统一导出 retrieval 包的公开数据模型、核心组件和工具函数。
- `_types.py`：定义 retrieval 内部共享的数据模型和枚举。
- `intent_analyzer.py`：分析用户查询意图，决定主查和辅查的记忆领域。
- `query_rewrite.py`：补全检索信号，包括主题、时间窗口、作用域过滤和 boost 信号。
- `fusion.py`：融合多个领域召回结果，并对重复记忆累加召回证据。
- `rerank.py`：对融合后的候选记忆做统一重排。
- `retrieval_trace.py`：记录完整检索链路，便于调试、评估和持久化。

## `__init__.py`

### 文件职责

该文件是 `src.retrieval` 包的公开入口，将内部数据模型、组件类和工具函数集中导出，方便其他模块通过 `from src.retrieval import ...` 使用。

### 导出内容

- 数据模型：`DomainRecallResult`、`FusedCandidate`、`IntentResult`、`MemoryDomain`、`MemoryItem`、`MemoryScope`、`RankedMemory`、`RetrievalQuery`、`RetrievalTrace`、`RewrittenQuery`、`TimeWindow`、`TraceStep`。
- 核心组件：`IntentAnalyzer`、`QueryRewriter`、`ResultFusion`、`Reranker`、`RetrievalTracer`。
- 工具函数：`trace_to_dict`。

该文件本身没有定义业务方法，主要通过 `__all__` 控制包级公开 API。

## `_types.py`

### 文件职责

定义 retrieval 包内共享的数据结构。其他模块基本都依赖这些类型来传递查询、意图、召回结果、融合候选、排序结果和追踪信息。

### `MemoryDomain`

记忆领域枚举，继承 `str` 和 `Enum`，便于序列化。

- `CLI_WORKFLOW`：命令行工作流、构建、部署、排障等记忆。
- `PROJECT_DECISION`：项目决策、方案选择、架构理由等记忆。
- `PERSONAL_PREFERENCE`：个人偏好、习惯、默认风格等记忆。
- `TEAM_RETENTION`：团队保留事项、提醒、合规、风险等记忆。

### `MemoryScope`

记忆作用域枚举。

- `USER`：用户级。
- `PROJECT`：项目级。
- `TEAM`：团队级。
- `WORKSPACE`：工作区级。
- `GLOBAL`：全局级。

### `MemoryStatus`

记忆状态字面量类型，允许值包括：

- `active`
- `candidate`
- `superseded`
- `expired`
- `forgotten`

### `MemoryItem`

从存储层加载后用于检索、融合和排序的记忆快照。

主要字段：

- `memory_id`：记忆唯一标识。
- `domain`：所属记忆领域。
- `memory_type`：记忆类型。
- `content_text`：记忆正文。
- `importance`：重要性分数，默认 `0.5`。
- `confidence`：置信度分数，默认 `0.5`。
- `status`：记忆状态，默认 `active`。
- `scope`：作用域，默认 `MemoryScope.USER`。
- `summary_text`：可选摘要。
- `freshness_score`：可选新鲜度分数。
- `tags`、`entities`：标签和实体，用于主题匹配。
- `source_ref`、`created_at`、`updated_at`：来源和时间信息。
- `extra`：领域 retriever 填充的扩展字段，例如 `user_id`、`project_id`、`repo_id`。

### `RetrievalQuery`

外部传入的原始检索请求。

主要字段：

- `query_text`：用户查询文本。
- `user_id`、`project_id`、`repo_id`、`workspace_id`、`team_id`：上下文标识。
- `session_context`：会话上下文。
- `timestamp`：查询时间戳。

### `IntentResult`

`IntentAnalyzer` 的输出。

主要字段：

- `primary_domains`：主查领域。
- `secondary_domains`：辅查领域。
- `intent_type`：意图类型标签，默认 `general`。
- `keywords`：识别出的关键词。
- `time_hint`：时间暗示，如 `recent`、`last_week`、`last_month`。
- `confidence`：意图识别置信度。

### `TimeWindow`

结构化时间窗口。

- `start`：开始时间。
- `end`：结束时间。
- `description`：时间窗口描述。

### `RewrittenQuery`

`QueryRewriter` 的输出。

主要字段：

- `original`：原始 `RetrievalQuery`。
- `rewritten_text`：改写后的查询文本。
- `extracted_topics`：提取出的主题词。
- `time_window`：推断出的时间窗口。
- `scope_filters`：作用域过滤条件。
- `boost_signals`：排序或召回阶段可使用的增强信号。

### `DomainRecallResult`

单个领域 retriever 的召回结果。

- `domain`：召回领域。
- `items`：召回到的 `MemoryItem` 列表。
- `recall_method`：召回方法名称，默认 `default`。
- `latency_ms`：召回耗时。

### `FusedCandidate`

跨领域融合后的候选记忆。

- `item`：候选记忆。
- `source_domain`：当前最强召回证据来自的领域。
- `domain_rank`：该记忆在来源领域中的排名。
- `fusion_score`：融合分数。

### `RankedMemory`

`Reranker` 的最终排序输出。

- `item`：记忆对象。
- `final_score`：最终分数。
- `score_breakdown`：各项分数明细。
- `rank`：最终名次，从 `1` 开始。

### `TraceStep`

检索链路中单个步骤的追踪记录。

- `name`：步骤名称。
- `start_time`、`end_time`、`duration_ms`：耗时信息。
- `input_summary`：输入摘要。
- `output_summary`：输出摘要。
- `metadata`：额外元数据。
- `children`：嵌套子步骤。

### `RetrievalTrace`

一次完整检索的链路追踪结果。

- `query_id`：查询 ID。
- `start_time`、`end_time`、`total_duration_ms`：整体耗时。
- `steps`：顶层步骤列表。
- `final_result_count`：最终结果数量。
- `metadata`：链路级元数据。

## `intent_analyzer.py`

### 文件职责

该文件负责把原始查询分类到合适的记忆领域，输出主查领域、辅查领域、关键词、时间暗示和置信度。它优先使用 LLM 结构化输出；如果没有 LLM 或调用失败，则降级为关键词规则。

### `_keyword_fallback(query: RetrievalQuery) -> IntentResult`

基于关键词规则的意图识别降级方法。

处理流程：

1. 将查询文本转为小写。
2. 遍历 `_KEYWORD_RULES`，统计每个 `MemoryDomain` 命中的关键词数量。
3. 按命中数量排序，选择命中最高的领域作为主查领域。
4. 如果第二名命中数达到第一名的一半，也加入主查领域。
5. 如果没有任何关键词命中，默认主查 `TEAM_RETENTION`，辅查 `PROJECT_DECISION`。
6. 如果只有一个主查领域且没有辅查领域，则根据 `_SECONDARY_AFFINITY` 补充辅查领域。
7. 调用 `_extract_time_hint` 提取时间暗示。
8. 根据最高命中数计算置信度，范围最高到 `0.8`。

返回值是 `IntentResult`，其中 `intent_type` 固定为 `keyword_matched`。

### `_extract_time_hint(text: str) -> str | None`

从文本中识别时间范围暗示。

识别规则：

- 命中“最近 / recently / 刚才 / just now / 今天 / today”时返回 `recent`。
- 命中“上周 / last week / 这周 / this week”时返回 `last_week`。
- 命中“上个月 / last month / 这个月 / this month”时返回 `last_month`。
- 没有命中则返回 `None`。

### `IntentAnalyzer`

意图分析器类。对外提供 `analyze` 方法，内部支持 LLM 策略和规则策略。

#### `__init__(self, llm_client: Any | None = None) -> None`

初始化意图分析器。

- `llm_client` 为 `None` 时，始终使用关键词规则。
- `llm_client` 不为 `None` 时，`analyze` 会优先调用 LLM。

#### `analyze(self, query: RetrievalQuery) -> IntentResult`

异步分析查询意图。

处理流程：

1. 如果存在 LLM client，调用 `_analyze_with_llm`。
2. 如果 LLM 调用成功，直接返回解析后的 `IntentResult`。
3. 如果 LLM 调用失败，记录 warning 日志。
4. 调用 `_keyword_fallback` 返回规则识别结果。

#### `_analyze_with_llm(self, query: RetrievalQuery) -> IntentResult`

使用 LLM 做结构化意图分类。

处理流程：

1. 调用 `_build_user_prompt` 构造用户 prompt。
2. 调用 `llm_client.ajson(...)`，传入系统 prompt、用户 prompt、JSON schema 和 `temperature=0`。
3. 调用 `_parse_llm_output` 将 LLM JSON 输出转为 `IntentResult`。

#### `_build_user_prompt(query: RetrievalQuery) -> str`

构造传给 LLM 的用户 prompt。

包含内容：

- `Query`：原始查询文本。
- `Project`：如果存在 `project_id`。
- `Repo`：如果存在 `repo_id`。
- `Context`：如果存在 `session_context`，将上下文键值对拼接为字符串。

#### `_parse_llm_output(raw: dict[str, Any]) -> IntentResult`

解析并清洗 LLM 输出。

处理逻辑：

- 只接受 `MemoryDomain` 枚举中存在的领域值。
- 如果 `primary_domains` 为空，默认使用 `TEAM_RETENTION`。
- 从 `secondary_domains` 中移除已经出现在主查领域里的领域。
- 如果主查只有 `TEAM_RETENTION` 且没有辅查，则补充 `PROJECT_DECISION`。
- 返回 `IntentResult`，包括 `intent_type`、`keywords`、`time_hint` 和 `confidence`。

## `query_rewrite.py`

### 文件职责

该文件负责将原始查询和意图分析结果扩展为更适合检索的结构化查询。输出内容包括改写文本、主题词、时间窗口、作用域过滤和 boost 信号。它同样优先使用 LLM，失败时降级为规则。

### `_compute_time_window(time_hint: str | None, reference: datetime | None = None) -> TimeWindow | None`

根据时间暗示推算具体时间窗口。

规则：

- `recent`：最近 3 天。
- `last_week`：最近 1 周。
- `last_month`：最近 30 天。

如果 `time_hint` 为空或不在规则表中，返回 `None`。否则以 `reference` 为结束时间；未传入 `reference` 时使用当前 UTC 时间。

### `_extract_scope_filters(query: RetrievalQuery) -> dict[str, str]`

从查询上下文中提取作用域过滤条件。

会提取以下非空字段：

- `user_id`
- `project_id`
- `repo_id`
- `workspace_id`
- `team_id`

返回字典用于后续召回或排序阶段的精确匹配。

### `_compute_boost_signals(intent: IntentResult, query: RetrievalQuery) -> dict[str, float]`

根据意图领域和上下文推导增强信号。

处理逻辑：

- 如果存在主查领域，使用第一个主查领域从 `_DOMAIN_DEFAULT_BOOSTS` 中获取默认 boost。
- 如果查询包含 `repo_id`，加入 `repo_match: 0.8`。
- 如果查询包含 `project_id`，加入 `project_match: 0.7`。

这些信号用于表达“哪些因素应该被额外加权”，例如新鲜度、主题匹配、仓库匹配等。

### `_extract_topics_by_rules(text: str) -> list[str]`

基于规则从文本中提取粗粒度 topic。

处理流程：

1. 将文本转为小写。
2. 使用正则提取英文、数字、连字符、点号组成的 token。
3. 过滤停用词和长度不大于 1 的 token。
4. 遍历 `_DOMAIN_TOPIC_TERMS`，如果领域关键词出现在文本中，则加入 topics。
5. 按出现顺序去重。
6. 最多返回前 15 个 topic。

该方法兼顾英文 token 和预设中文领域词。

### `QueryRewriter`

查询改写器类，对外提供 `rewrite` 方法。

#### `__init__(self, llm_client: Any | None = None) -> None`

初始化查询改写器。

- `llm_client` 为 `None` 时，只使用规则改写。
- `llm_client` 不为 `None` 时，优先调用 LLM。

#### `rewrite(self, query: RetrievalQuery, intent: IntentResult) -> RewrittenQuery`

异步改写查询。

处理流程：

1. 调用 `_extract_scope_filters` 提取作用域过滤。
2. 如果存在 LLM client，调用 `_rewrite_with_llm`。
3. 如果 LLM 改写失败，记录 warning 日志并降级。
4. 调用 `_rewrite_by_rules` 返回规则改写结果。

#### `_rewrite_with_llm(self, query: RetrievalQuery, intent: IntentResult, scope_filters: dict[str, str]) -> RewrittenQuery`

使用 LLM 提取结构化检索信号。

处理流程：

1. 调用 `_build_user_prompt` 构造 prompt。
2. 调用 `llm_client.ajson(...)`，要求输出符合 `_REWRITE_JSON_SCHEMA`。
3. 如果 LLM 返回 `time_start` 或 `time_end`，构造 `TimeWindow`。
4. 如果 LLM 没有返回时间窗口但意图中有 `time_hint`，使用 `_compute_time_window` 补充。
5. 调用 `_compute_boost_signals` 生成规则 boost。
6. 合并 LLM boost 和规则 boost；同名 key 下规则 boost 会覆盖 LLM boost。
7. 返回 `RewrittenQuery`。

#### `_rewrite_by_rules(self, query: RetrievalQuery, intent: IntentResult, scope_filters: dict[str, str]) -> RewrittenQuery`

使用规则策略改写查询。

处理流程：

1. 调用 `_extract_topics_by_rules` 从原始查询提取主题。
2. 将 `intent.keywords` 追加到主题列表，并做大小写去重。
3. 根据 `intent.time_hint` 调用 `_compute_time_window`。
4. 调用 `_compute_boost_signals` 生成 boost。
5. 返回 `RewrittenQuery`，其中 `rewritten_text` 保持原始查询文本。

#### `_build_user_prompt(query: RetrievalQuery, intent: IntentResult) -> str`

构造用于 LLM 查询改写的用户 prompt。

包含内容：

- `Original query`：原始查询。
- `Detected intent`：意图类型。
- `Primary domains`：主查领域。
- `Keywords`：如果存在关键词。
- `Time hint`：如果存在时间暗示。
- `Project`：如果存在项目 ID。
- `Repo`：如果存在仓库 ID。
- `Session context`：如果存在会话上下文。

## `fusion.py`

### 文件职责

该文件负责把多个领域 retriever 的召回结果融合为统一候选列表。融合算法使用 Reciprocal Rank Fusion（RRF），并叠加主查、辅查、非相关领域权重。重复召回到同一 `memory_id` 时，会累加融合分数。

### `ResultFusion`

跨领域结果融合器。

#### `__init__(self, *, rrf_k: int = 60, primary_weight: float = 1.0, secondary_weight: float = 0.5, unrelated_weight: float = 0.2) -> None`

初始化融合器。

参数含义：

- `rrf_k`：RRF 公式中的常数，控制排名靠后结果的衰减速度。
- `primary_weight`：主查领域权重。
- `secondary_weight`：辅查领域权重。
- `unrelated_weight`：既不是主查也不是辅查的兜底权重。

#### `fuse(self, recalls: list[DomainRecallResult], intent: IntentResult) -> list[FusedCandidate]`

融合多个领域召回结果。

处理流程：

1. 从 `intent` 中取出主查领域集合和辅查领域集合。
2. 遍历每个领域的 `DomainRecallResult`。
3. 调用 `_get_domain_weight` 获取该领域权重。
4. 遍历该领域召回的 `items`，根据领域内排名调用 `_rrf_score`。
5. 计算 `fusion_score = rrf_score * domain_weight`。
6. 如果该 `memory_id` 首次出现，创建 `FusedCandidate`。
7. 如果重复出现，累加到已有候选的 `fusion_score`。
8. 对重复候选，若当前单路召回分数更高，则更新 `source_domain` 和 `domain_rank`。
9. 按 `fusion_score` 降序返回候选列表。

#### `_rrf_score(self, rank: int) -> float`

计算 RRF 分数。

公式为：

```text
1 / (rrf_k + rank + 1)
```

其中 `rank` 从 `0` 开始。排名越靠前，分数越高。

#### `_get_domain_weight(self, domain: MemoryDomain, primary_set: set[MemoryDomain], secondary_set: set[MemoryDomain]) -> float`

根据领域与意图的关系返回权重。

- 如果领域在主查集合中，返回 `primary_weight`。
- 如果领域在辅查集合中，返回 `secondary_weight`。
- 否则返回 `unrelated_weight`。

## `rerank.py`

### 文件职责

该文件负责对融合后的候选记忆进行最终重排。默认使用多因子加权打分；如果配置了 LLM 且启用 LLM 重排，会对前若干候选做 listwise 语义重排，并把 LLM 排名转换为额外 bonus 加到原分数上。

### `_score_fusion(candidate: FusedCandidate) -> float`

将融合阶段的 `fusion_score` 转为 `[0, 1]` 范围内的排序因子。

当前实现为：

```text
min(candidate.fusion_score * 60, 1.0)
```

### `_score_importance(candidate: FusedCandidate) -> float`

返回候选记忆自身的 `importance` 分数。

### `_score_confidence(candidate: FusedCandidate) -> float`

返回候选记忆自身的 `confidence` 分数。

### `_score_freshness(candidate: FusedCandidate) -> float`

计算新鲜度分数。

处理逻辑：

- 如果 `candidate.item.freshness_score` 不为空，直接使用它。
- 否则优先使用 `updated_at`，没有则使用 `created_at`。
- 如果没有时间信息，返回默认值 `0.3`。
- 如果时间可解析，则按 30 天半衰期做指数衰减，越新的记忆分数越高。
- 如果时间解析失败，返回默认值 `0.3`。

### `_score_topic_overlap(candidate: FusedCandidate, query: RewrittenQuery) -> float`

计算查询主题与记忆标签、实体、正文的重叠度。

处理逻辑：

1. 如果 `query.extracted_topics` 为空，返回 `0.0`。
2. 将查询 topics 转为小写集合。
3. 将候选记忆的 `tags` 和 `entities` 转为小写集合。
4. 如果某个查询 topic 出现在 `content_text` 中，也加入候选项集合。
5. 返回重叠数量除以查询 topic 总数。

### `_score_scope_match(candidate: FusedCandidate, query: RewrittenQuery) -> float`

计算作用域过滤匹配度。

处理逻辑：

- 如果查询没有 `scope_filters`，返回 `0.5`。
- 遍历每个 scope filter，检查候选记忆的 `extra` 中是否有完全相等的值。
- 对 `user_id` 有特殊处理：仅 `scope == USER` 不加分，必须 `extra["user_id"]` 精确匹配才算命中。
- 返回命中数量除以过滤条件总数。

### `Reranker`

跨领域统一重排器。

#### `__init__(self, llm_client: Any | None = None, *, factor_weights: dict[str, float] | None = None, use_llm_rerank: bool = False) -> None`

初始化重排器。

参数含义：

- `llm_client`：可选 LLM client。
- `factor_weights`：多因子打分权重；为空时使用 `DEFAULT_FACTOR_WEIGHTS`。
- `use_llm_rerank`：是否启用 LLM listwise 重排。只有该参数为 `True` 且 `llm_client` 不为空时才生效。

#### `rerank(self, candidates: list[FusedCandidate], query: RewrittenQuery, *, top_k: int = 10) -> list[RankedMemory]`

异步重排候选列表并返回前 `top_k` 条。

处理流程：

1. 如果候选为空，返回空列表。
2. 调用 `_multi_factor_score` 计算基础分。
3. 如果启用 LLM 重排，先按基础分降序排序，再调用 `_llm_rerank`。
4. 如果 LLM 重排失败，记录 warning 日志并继续使用基础分。
5. 再次按 `final_score` 降序排序。
6. 截取前 `top_k` 条。
7. 为结果设置从 `1` 开始的 `rank`。

#### `_multi_factor_score(self, candidates: list[FusedCandidate], query: RewrittenQuery) -> list[RankedMemory]`

对每个候选计算多因子加权分。

使用因子包括：

- `fusion`
- `importance`
- `confidence`
- `freshness`
- `topic_overlap`
- `scope_match`

处理流程：

1. 根据候选来源领域调用 `_get_effective_weights` 获取有效权重。
2. 分别调用各 `_score_*` 函数生成 `score_breakdown`。
3. 按权重加权求和得到 `final_score`。
4. 封装为 `RankedMemory`。

#### `_get_effective_weights(self, domain: MemoryDomain) -> dict[str, float]`

合并默认权重和领域级权重覆盖，并归一化。

处理逻辑：

- 如果该领域没有覆盖配置，直接归一化当前默认权重。
- 如果存在 `_DOMAIN_WEIGHT_OVERRIDES`，用领域配置覆盖默认权重。
- 调用 `_normalize_weights` 保证正权重之和为 `1`。

#### `_normalize_weights(weights: dict[str, float]) -> dict[str, float]`

静态方法，用于归一化权重。

处理逻辑：

- 只统计大于 `0` 的权重。
- 如果正权重总和小于等于 `0`，原样返回。
- 否则将每个正权重除以总和，非正权重置为 `0.0`。

#### `_llm_rerank(self, scored: list[RankedMemory], query: RewrittenQuery) -> list[RankedMemory]`

使用 LLM 对前若干候选进行 listwise 语义重排。

处理流程：

1. 取前 `_LLM_RERANK_WINDOW` 个候选，当前窗口大小为 `20`。
2. 如果窗口内候选不超过 1 个，直接返回原列表。
3. 调用 `_build_rerank_prompt` 构造候选列表 prompt。
4. 调用 `llm_client.ajson(...)`，要求返回 `ranked_ids`。
5. 将 LLM 返回的 ID 顺序转换为排名。
6. 对窗口内命中的候选计算 bonus：`1.0 / (llm_rank + 1)`。
7. 将 bonus 写入 `score_breakdown["llm_rerank"]`。
8. 将 `bonus * 0.15` 加到 `final_score` 上。

该方法不会完全替代多因子分数，而是在基础分上叠加语义重排奖励。

#### `_build_rerank_prompt(candidates: list[RankedMemory], query: RewrittenQuery) -> str`

静态方法，构造 LLM 重排 prompt。

内容包括：

- 用户查询：优先使用 `query.rewritten_text`，为空时使用 `query.original.query_text`。
- 候选记忆列表：每条包含 `memory_id`、领域和正文。
- 候选正文优先使用 `summary_text`，没有则使用 `content_text`。
- 单条候选文本超过 200 字符时截断并追加省略号。

## `retrieval_trace.py`

### 文件职责

该文件提供检索链路追踪能力。调用方可以用 context manager 记录每个步骤的输入、输出、耗时、嵌套结构和异常信息。最终 trace 可保存在内存中，也可以通过回调持久化。

### `TraceContext`

管理一次检索请求的完整链路追踪上下文。

#### `__init__(self, query_id: str) -> None`

初始化单次查询追踪上下文。

会设置：

- `_query_id`：查询 ID。
- `_start`：开始时间，使用 `time.monotonic()`。
- `_steps`：顶层步骤列表。
- `_step_stack`：嵌套步骤栈。
- `_finished`：是否结束。
- `_metadata`：链路级元数据。
- `_result_count`：最终结果数量。

#### `step(self, name: str, *, input_summary: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None) -> Generator[StepHandle, None, None]`

记录一个检索步骤的 context manager，支持嵌套。

使用方式类似：

```python
with ctx.step("rerank") as step:
    step.set_output({"result_count": 5})
```

处理流程：

1. 创建 `TraceStep`，记录名称、开始时间、输入摘要和元数据。
2. 创建 `StepHandle` 并压入 `_step_stack`。
3. 将 handle 交给调用方设置输入、输出或元数据。
4. 如果步骤内抛出异常，把异常字符串写入 `metadata["error"]` 后继续抛出。
5. 在 finally 中记录结束时间和耗时。
6. 从栈中弹出当前步骤。
7. 如果仍有父步骤，则把当前步骤加入父步骤 `children`。
8. 否则加入顶层 `_steps`。

#### `set_metadata(self, key: str, value: Any) -> None`

设置链路级元数据。

示例用途：记录检索策略、用户上下文、实验配置等。

#### `set_result_count(self, count: int) -> None`

设置最终结果数量，最终会写入 `RetrievalTrace.final_result_count`。

#### `finish(self) -> RetrievalTrace`

结束追踪并返回完整 `RetrievalTrace`。

处理逻辑：

- 如果已经结束，返回 `self.trace`。
- 否则设置 `_finished = True`。
- 记录结束时间。
- 构造并返回包含总耗时、步骤列表、结果数量和元数据的 `RetrievalTrace`。

#### `trace(self) -> RetrievalTrace`

只读属性，返回当前 trace。

行为：

- 如果尚未结束，会调用 `finish()` 结束并返回。
- 如果已经结束，会根据已有步骤重新构造 `RetrievalTrace`。
- 已结束分支中，`end_time` 使用最后一个顶层步骤的结束时间；如果没有步骤则使用开始时间。
- 已结束分支中，`total_duration_ms` 使用顶层步骤耗时求和。

### `StepHandle`

`TraceContext.step` 返回的句柄，用于在步骤执行期间补充输入、输出和元数据。

#### `__init__(self, step: TraceStep) -> None`

保存当前步骤对象引用。

#### `set_input(self, data: dict[str, Any]) -> None`

把传入字典合并到当前步骤的 `input_summary`。

#### `set_output(self, data: dict[str, Any]) -> None`

把传入字典合并到当前步骤的 `output_summary`。

#### `set_metadata(self, key: str, value: Any) -> None`

设置当前步骤的单个元数据字段。

### `RetrievalTracer`

检索链路追踪器，负责创建 `TraceContext`、保存最近 trace，并可调用持久化回调。

#### `__init__(self, persist_fn: Any | None = None) -> None`

初始化追踪器。

参数：

- `persist_fn`：可选持久化函数，签名预期为 `(trace_dict: dict) -> None`。

内部状态：

- `_recent_traces`：最近 trace 列表。
- `_max_recent`：最多保留 100 条。

#### `start_trace(self, query_id: str | None = None) -> Generator[TraceContext, None, None]`

启动一次检索追踪的 context manager。

处理流程：

1. 如果没有传入 `query_id`，自动生成形如 `q-<12位uuid>` 的 ID。
2. 创建 `TraceContext`。
3. 将上下文交给调用方使用。
4. context 退出时调用 `ctx.finish()`。
5. 调用 `_store` 保存 trace。

#### `_store(self, trace: RetrievalTrace) -> None`

保存一次 trace。

处理逻辑：

- 追加到 `_recent_traces`。
- 如果超过 `_max_recent`，只保留最后 100 条。
- 如果设置了 `persist_fn`，调用 `trace_to_dict(trace)` 后传给持久化函数。
- 如果持久化失败，记录 warning 日志，但不影响主流程。

#### `recent_traces(self) -> list[RetrievalTrace]`

只读属性，返回最近 trace 的浅拷贝列表，避免调用方直接修改内部列表。

#### `get_trace(self, query_id: str) -> RetrievalTrace | None`

按 `query_id` 查找最近 trace。

处理逻辑：

- 从 `_recent_traces` 尾部向前查找，优先返回最新匹配项。
- 找不到时返回 `None`。

### `_step_to_dict(step: TraceStep) -> dict[str, Any]`

将单个 `TraceStep` 序列化为可 JSON 化字典。

输出字段：

- `name`
- `duration_ms`：保留两位小数。
- `input_summary`
- `output_summary`
- `metadata`
- `children`：递归序列化子步骤。

### `trace_to_dict(trace: RetrievalTrace) -> dict[str, Any]`

将完整 `RetrievalTrace` 序列化为可 JSON 化字典。

输出字段：

- `query_id`
- `total_duration_ms`：保留两位小数。
- `final_result_count`
- `steps`：通过 `_step_to_dict` 序列化。
- `metadata`

## 检索链路中的典型调用顺序

1. `IntentAnalyzer.analyze`：识别查询属于哪些记忆领域。
2. `QueryRewriter.rewrite`：补全 topic、时间窗口、scope filter 和 boost。
3. 各领域 retriever 返回 `DomainRecallResult`。
4. `ResultFusion.fuse`：把多领域召回合并为 `FusedCandidate`。
5. `Reranker.rerank`：计算最终排序并返回 `RankedMemory`。
6. `RetrievalTracer` / `TraceContext`：在上述各阶段外围记录链路耗时和中间结果。

