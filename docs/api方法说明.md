# api 模块方法说明

本文档介绍 `src/api` 目录下每个 Python 文件、函数和路由方法的职责。该目录是 Memory Engine 的 HTTP API 层，负责把 FastAPI 请求转换为 schema/store 操作，并返回统一响应。

## 目录总览

- `__init__.py`：保留 API 包入口，目前不导出对象。
- `benchmark.py`：提供 benchmark 运行与状态查询的占位接口。
- `health.py`：提供服务健康检查接口，检查存储、Embedding 和 LLM 依赖状态。
- `ingest.py`：提供事件写入接口，将外部请求转换为 `NormalizedEvent` 并落库。
- `proactive.py`：提供主动建议接口的占位实现。
- `retrieve.py`：提供记忆检索接口和搜索别名接口，目前使用 `MemoryCoreStore` 的本地 fallback 检索。
- `update.py`：提供记忆状态、置信度、重要性、替换关系和反馈更新接口。

## `__init__.py`

### 文件职责

该文件用于标记 `src.api` 为包，并通过 `__all__ = []` 明确当前没有包级公共导出。

## `benchmark.py`

### 文件职责

该文件定义 benchmark 相关路由。当前只实现 dry-run 接收与状态占位查询，还没有接入真实评测执行器。

### `_new_run_id() -> str`

生成一次 benchmark run 的唯一 ID。

处理逻辑：
1. 调用 `uuid.uuid4()` 生成随机 UUID。
2. 取 UUID hex 的前 12 位。
3. 拼接 `bench-` 前缀并返回。

### `run_benchmark(request: BenchmarkRunRequest) -> BenchmarkRunResponse`

处理 `POST /api/v1/benchmark/run`。

处理逻辑：
1. 如果 `request.dry_run` 为真，返回 `accepted=True`，状态为 `accepted`，表示 dry-run 请求已被接受。
2. 如果不是 dry-run，返回 `accepted=False`，状态为 `not_implemented`，说明真实 benchmark runner 尚未实现。
3. 两种分支都会生成新的 `run_id`，并回传请求中的 `suite_name`。

### `get_benchmark_status(run_id: str) -> BenchmarkStatusResponse`

处理 `GET /api/v1/benchmark/{run_id}`。

当前行为：
- 返回 `status="ok"`。
- 原样回传 `run_id`。
- `state` 固定为 `not_found`。
- `result` 固定为 `None`。
- `message` 表示 benchmark runner 尚未实现。

## `health.py`

### 文件职责

该文件定义健康检查路由，汇总应用配置、数据库存储、Embedding Store 和 LLM Client 的可用性。

### `_check_store(store: EventStore | MemoryCoreStore) -> dict[str, Any]`

检查 SQLite store 是否可用。

处理逻辑：
1. 调用 `store.fetch_one("SELECT 1 AS ok")` 做最小查询。
2. 查询成功时返回 `{"available": True}`。
3. 查询抛出异常时捕获异常，返回 `{"available": False, "error": str(exc)}`。

### `health_check(...) -> dict[str, Any]`

处理 `GET /health`。

处理逻辑：
1. 通过 FastAPI `Depends` 获取配置、事件存储、记忆存储、Embedding Store 和 LLM Client。
2. 分别调用 `_check_store` 检查 `event_store` 和 `memory_core_store`。
3. 只有两个核心存储都可用时，整体 `status` 才是 `ok`，否则为 `degraded`。
4. 返回应用名、环境、存储状态、Embedding 启用/可用状态和 LLM 启用/可用状态。

## `ingest.py`

### 文件职责

该文件定义事件写入 API。它接收 `IngestRequest`，补齐事件 ID 和发生时间，转换为 `NormalizedEvent` 后写入 `EventStore`。

### `_new_event_id() -> str`

生成事件 ID。

处理逻辑：
1. 调用 `uuid.uuid4()`。
2. 取 UUID hex 前 12 位。
3. 拼接 `evt-` 前缀。

### `_utc_now_iso() -> str`

返回当前 UTC 时间的 ISO 字符串。

处理逻辑：
1. 调用 `datetime.now(timezone.utc)` 获取带 UTC 时区的当前时间。
2. 调用 `.isoformat()` 转成字符串。

### `_model_to_dict(model: object) -> dict[str, object]`

兼容 Pydantic v1/v2 的模型转字典方法。

处理逻辑：
1. 如果对象有 `model_dump` 方法，调用它。
2. 否则调用 `dict()`。

### `ingest_event(request: IngestRequest, event_store: EventStore) -> IngestResponse`

处理 `POST /api/v1/ingest`。

处理逻辑：
1. 使用请求内的 `event_id`，如果为空则调用 `_new_event_id` 生成。
2. 使用请求内的 `occurred_at`，如果为空则调用 `_utc_now_iso`。
3. 将请求字段组装成 `NormalizedEvent`，其中 `context` 会先通过 `_model_to_dict` 转成字典再构造 `EventContext`。
4. 调用 `event_store.insert_event(event)` 写入事件。
5. 如果 SQLite 唯一约束冲突，返回 HTTP 409，说明 `event_id` 已存在。
6. 如果其他存储异常，返回 HTTP 500。
7. 成功时返回 `stored=True`，并把 `memory_candidates` 固定为 `0`。

## `proactive.py`

### 文件职责

该文件定义主动建议 API 的占位实现。当前只校验查询参数并返回空建议列表。

### `get_proactive_suggestions(...) -> ProactiveResponse`

处理 `GET /api/v1/proactive`。

参数：
- `user_id`：可选用户 ID。
- `project_id`：可选项目 ID。
- `team_id`：可选团队 ID。
- `limit`：建议数量限制，FastAPI 约束为 `1 <= limit <= 50`，默认 `10`。

当前行为：
1. 丢弃所有参数。
2. 返回 `status="ok"`。
3. `suggestions` 固定为空列表。
4. `message` 表示 proactive scheduler 尚未实现。

## `retrieve.py`

### 文件职责

该文件定义记忆检索 API。当前没有接入完整 domain retriever 链路，而是从 `MemoryCoreStore` 拉取 active 记忆并做简单文本重叠打分。

### `_new_query_id() -> str`

生成检索请求 ID。

处理逻辑：
1. 调用 `uuid.uuid4()`。
2. 取 UUID hex 前 12 位。
3. 拼接 `qry-` 前缀。

### `_score_memory(row: dict[str, Any], query_text: str) -> tuple[float, dict[str, float]]`

对单条记忆行做 fallback 检索打分。

处理逻辑：
1. 取 `content_text` 和 `summary_text` 并转成小写。
2. 将查询文本按空白切分成 terms。
3. 统计有多少 term 出现在正文或摘要中，得到 `text_overlap`。
4. 读取 `importance` 和 `confidence`，缺失时按 `0.0`。
5. 计算总分：`text_overlap * 0.5 + importance * 0.25 + confidence * 0.25`。
6. 返回总分和分项得分字典。

### `_retrieve_fallback(request: RetrieveRequest, memory_store: MemoryCoreStore) -> RetrieveResponse`

执行当前版本的本地 fallback 检索。

处理流程：
1. 生成新的 `query_id`。
2. 调用 `memory_store.list_active_memories` 拉取 active 记忆，数量为 `max(top_k * 5, 20)`。
3. 对每条记录调用 `_score_memory`。
4. 按总分降序排序。
5. 截取前 `top_k` 条，封装为 `MemoryHit`，rank 从 `1` 开始。
6. 如果 `request.include_trace` 为真，返回包含模式、候选数和结果数的简单 trace。
7. 返回 `RetrieveResponse`，message 标明当前使用 memory_core fallback。

### `retrieve_memories(...) -> RetrieveResponse`

处理 `POST /api/v1/retrieve`。

处理逻辑：
1. 通过依赖获取 `MemoryCoreStore` 和可选 LLM Client。
2. 启用 LLM 时走 IntentAnalyzer → QueryRewriter → Reranker 检索管线。
3. 如果 `query_text` 去空白后为空，抛出 HTTP 422。
4. 调用 `_retrieve_fallback` 返回检索结果。

### `search_memories_alias(...) -> RetrieveResponse`

处理 `POST /api/v1/memories/search`。

该方法是 `retrieve_memories` 的别名路由，直接转调用 `retrieve_memories`，保持同样的请求、依赖和返回格式。

## `update.py`

### 文件职责

该文件定义记忆更新 API。当前支持 expire、forget、supersede、confidence、importance 的真实 store 更新；feedback 和 correct 为占位接收。

### `_require(value: str | float | None, name: str) -> None`

检查必填字段是否存在。

处理逻辑：
- 如果 `value is None`，抛出 HTTP 400，错误信息为 `<name> is required`。
- 非 `None` 时不返回任何内容。

### `_update_memory_core(request: MemoryUpdateRequest, memory_store: MemoryCoreStore) -> MemoryUpdateResponse`

执行具体更新动作。

处理流程：
1. 读取 `request.action`。
2. `expire`：要求 `memory_id`，调用 `update_memory_status(memory_id, "expired")`。
3. `forget`：要求 `memory_id`，调用 `update_memory_status(memory_id, "forgotten")`。
4. `supersede`：要求 `memory_id` 和 `new_memory_id`，调用 `mark_superseded` 建立替换关系。
5. `confidence`：要求 `memory_id` 和 `confidence`，调用 `update_confidence`。
6. `importance`：要求 `memory_id` 和 `importance`，调用 `update_importance`。
7. `feedback`：返回 `accepted`，表示反馈已接收，但 access log store 尚未实现。
8. `correct`：返回 `accepted`，表示修正已接收，但核心生命周期服务尚未实现。
9. 如果 store 操作发生非 HTTP 异常，统一返回 HTTP 500。
10. 如果 action 不支持，返回 HTTP 400。

### `update_memory(...) -> MemoryUpdateResponse`

处理 `POST /api/v1/update`。

行为：通过依赖获取 `MemoryCoreStore`，然后调用 `_update_memory_core`。

### `update_memory_alias(...) -> MemoryUpdateResponse`

处理 `POST /api/v1/memories/update`。

该方法是 `update_memory` 的别名路由，同样调用 `_update_memory_core`。
