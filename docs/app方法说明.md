# app 模块方法说明

本文档介绍 `src/app` 目录下每个 Python 文件、类和方法的职责。该目录是 Memory Engine 的应用装配层，负责配置读取、依赖缓存、日志中间件、FastAPI app 创建和服务启动。

## 目录总览

- `__init__.py`：保留 app 包入口，目前不导出对象。
- `config.py`：定义应用配置结构和环境变量解析逻辑。
- `dependencies.py`：定义 FastAPI 依赖工厂，并用 `lru_cache` 缓存配置、store 和 LLM Client。
- `logging.py`：定义基础日志配置、请求 ID 提取和请求日志中间件。
- `main.py`：创建 FastAPI app，注册 API router，提供内置健康检查 fallback 和 `uvicorn` 启动入口。

## `__init__.py`

### 文件职责

该文件用于标记 `src.app` 为包，并通过 `__all__ = []` 明确当前没有包级公共导出。

## `config.py`

### 文件职责

该文件集中管理应用配置。默认值适合本地运行，`load_settings` 会从 `LARKMEMORY_*` 环境变量读取覆盖项。

### `AppSettings`

应用配置 dataclass，使用 `slots=True` 降低实例动态属性风险。

主要字段：
- `app_name`、`env`、`host`、`port`、`debug`：应用基础信息和启动参数。
- `data_dir`、`sqlite_path`：本地数据目录和 SQLite 路径。
- `chroma_dir`、`chroma_collection`：Embedding Store 的持久化目录和集合名。
- `llm_api_key`、`llm_model`、`llm_base_url`、`llm_timeout`、`llm_max_retries`：LLM Client 配置。
- `enable_llm`、`enable_embedding`：是否启用 LLM 和 Embedding。
- `log_level`、`request_log_enabled`：日志级别和请求日志中间件开关。

### `_env_str(name: str, default: str | None) -> str | None`

读取字符串环境变量。

处理逻辑：
1. 环境变量不存在时返回 `default`。
2. 环境变量存在但为空字符串时返回 `None`。
3. 其他情况返回原始字符串。

### `_env_int(name: str, default: int) -> int`

读取整数环境变量。

处理逻辑：
1. 环境变量不存在或为空字符串时返回 `default`。
2. 尝试用 `int(value)` 转换。
3. 转换失败时抛出带环境变量名的 `ValueError`。

### `_env_float(name: str, default: float) -> float`

读取浮点数环境变量。

处理逻辑：
1. 环境变量不存在或为空字符串时返回 `default`。
2. 尝试用 `float(value)` 转换。
3. 转换失败时抛出带环境变量名的 `ValueError`。

### `_env_bool(name: str, default: bool) -> bool`

读取布尔环境变量。

识别规则：
- `1`、`true`、`yes`、`on` 返回 `True`。
- `0`、`false`、`no`、`off` 返回 `False`。
- 不存在或为空字符串时返回 `default`。
- 其他值抛出带环境变量名的 `ValueError`。

### `load_settings() -> AppSettings`

从环境变量构建完整 `AppSettings`。

处理逻辑：
1. 逐项读取 `LARKMEMORY_*` 环境变量。
2. 对字符串、整数、浮点数、布尔值分别调用 `_env_*` 工具函数。
3. 对关键字符串字段使用非空 fallback，例如 app name、host、sqlite path。
4. 返回填充后的 `AppSettings` 实例。

## `dependencies.py`

### 文件职责

该文件提供 FastAPI 依赖工厂。所有工厂都使用 `@lru_cache(maxsize=1)`，避免每次请求重复创建配置和存储对象。

### `get_settings() -> AppSettings`

加载并缓存应用配置。

行为：调用 `load_settings()`，后续调用返回同一个缓存对象，直到 `reset_dependency_cache()` 被调用。

### `get_event_store() -> EventStore`

创建并缓存事件存储。

处理逻辑：
1. 读取 `get_settings().sqlite_path`。
2. 创建 `EventStore`。
3. 调用 `create_table()` 确保表存在。
4. 返回 store。

### `get_memory_core_store() -> MemoryCoreStore`

创建并缓存核心记忆存储。

处理逻辑：
1. 读取 `get_settings().sqlite_path`。
2. 创建 `MemoryCoreStore`。
3. 调用 `create_table()` 确保表存在。
4. 返回 store。

### `get_embedding_store() -> EmbeddingStore | None`

按配置创建 Embedding Store。

处理逻辑：
1. 如果 `settings.enable_embedding` 为假，返回 `None`。
2. 否则使用 `chroma_collection` 和 `chroma_dir` 创建 `EmbeddingStore`。

### `get_llm_client() -> LLMClient | None`

按配置创建 LLM Client。

处理逻辑：
1. 如果 `settings.enable_llm` 为假，返回 `None`。
2. 如果缺少 `llm_api_key` 或 `llm_model`，返回 `None`。
3. 调用 `LLMClient.from_openai_compatible` 创建 OpenAI-compatible client。
4. 传入 base URL、timeout 和 max retries 配置。

### `reset_dependency_cache() -> None`

清空所有依赖工厂缓存。

会清理：
- `get_settings`
- `get_event_store`
- `get_memory_core_store`
- `get_embedding_store`
- `get_llm_client`

该方法主要用于测试或配置切换后重新加载依赖。

## `logging.py`

### 文件职责

该文件提供基础日志配置和请求日志中间件。请求日志会记录方法、路径、状态码、耗时、客户端 IP 和 request id。

### `setup_logging(level: str = "INFO") -> None`

配置根 logger。

处理逻辑：
1. 从 `logging` 模块中解析日志级别，解析失败时使用 `logging.INFO`。
2. 设置 root logger 级别。
3. 创建统一 formatter：时间、级别、logger 名称和消息。
4. 查找是否已有带 `_larkmemory_handler` 标记的 handler。
5. 如果没有，则创建输出到 `sys.stdout` 的 `StreamHandler` 并打标。
6. 设置 handler 级别和 formatter。

### `get_request_id(headers: Mapping[str, str] | Headers) -> str`

从请求头中提取 request id。

处理逻辑：
1. 优先读取 `x-request-id`。
2. 其次读取 `x-larkmemory-request-id`。
3. 如果对应 header 存在且非空，返回去空白后的值。
4. 如果都不存在，生成 `req-<12位uuid>`。

### `RequestLogMiddleware`

FastAPI/Starlette 请求日志中间件。

#### `__init__(self, app: Callable, logger_name: str = "larkmemory.request") -> None`

初始化中间件。

处理逻辑：
1. 调用父类 `BaseHTTPMiddleware` 初始化。
2. 根据 `logger_name` 获取 logger，默认使用 `larkmemory.request`。

#### `dispatch(self, request: Request, call_next: Callable) -> Response`

包裹单次 HTTP 请求。

处理流程：
1. 调用 `get_request_id` 获取或生成 request id。
2. 用 `time.perf_counter()` 记录开始时间。
3. 调用下游 `call_next(request)`。
4. 如果下游抛出异常，记录异常日志、耗时、方法、路径、客户端和 request id，然后继续抛出异常。
5. 请求成功时计算耗时。
6. 在响应头写入 `x-request-id`。
7. 记录 info 级别请求日志。
8. 返回响应。

## `main.py`

### 文件职责

该文件是 FastAPI 应用入口。它负责装配配置、日志、中间件和 API router，并提供命令行启动函数。

### `create_app(settings: AppSettings | None = None) -> FastAPI`

创建 FastAPI 应用实例。

处理流程：
1. 使用传入的 `settings`，如果为空则调用 `get_settings()`。
2. 调用 `setup_logging` 初始化日志。
3. 创建 `FastAPI`，设置 title 和 debug。
4. 将配置保存到 `app.state.settings`。
5. 如果 `request_log_enabled` 为真，添加 `RequestLogMiddleware`。
6. 调用 `register_routers(app)` 注册 API 路由。
7. 如果注册后仍没有 `GET /health`，调用 `register_builtin_health_route` 添加内置 fallback。
8. 返回 app。

### `register_routers(app: FastAPI) -> list[str]`

按 `ROUTER_MODULES` 动态注册 API router。

处理流程：
1. 遍历模块名列表。
2. 调用 `importlib.import_module` 动态导入模块。
3. 如果目标 API 模块本身不存在，跳过。
4. 如果导入过程中缺失的是其他依赖模块，则继续抛出异常。
5. 从模块读取 `router` 属性。
6. 没有 router 时记录 warning 并跳过。
7. 有 router 时调用 `app.include_router(router)`。
8. 返回已注册模块的短名称列表。

### `register_builtin_health_route(app: FastAPI) -> None`

注册内置 `/health` fallback 路由。

内部路由 `health() -> dict[str, object]` 的行为：
1. 从 `app.state.settings` 读取配置。
2. 返回 `status`、应用名、环境、LLM 开关和 Embedding 开关。

### `has_route(app: FastAPI, path: str, method: str) -> bool`

检查 app 是否已存在指定 path 和 HTTP method 的路由。

处理逻辑：
1. 将 method 转成大写。
2. 遍历 `app.routes`。
3. 读取每个 route 的 `path` 和 `methods`。
4. 如果路径相同且 method 存在于 route methods 中，返回 `True`。
5. 遍历结束仍未命中时返回 `False`。

### `main() -> None`

命令行启动入口。

处理流程：
1. 调用 `get_settings()` 获取配置。
2. 尝试导入 `uvicorn`。
3. 如果缺少 `uvicorn`，抛出 `RuntimeError("Missing dependency: uvicorn")`。
4. 调用 `uvicorn.run` 启动 `src.app.main:app`。
5. 使用配置中的 host、port 和 debug reload。

### `app = create_app()`

模块导入时创建默认 FastAPI app，供 `uvicorn src.app.main:app` 使用。
