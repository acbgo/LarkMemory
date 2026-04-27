# utils 模块方法说明

本文档介绍 `src/utils` 目录下每个 Python 文件、函数和方法的职责。该目录提供项目内通用工具，包括 ID、JSON 日志、文本清洗和 UTC 时间处理。

## 目录总览

- `__init__.py`：统一导出常用工具函数。
- `ids.py`：生成和解析带类型前缀的 ID。
- `jsonlog.py`：把对象安全转换为 JSON，并输出结构化日志。
- `text.py`：文本清洗、截断、标签拆分和关键词匹配。
- `time.py`：UTC 时间生成、ISO 格式化、解析、时间窗口和过期判断。

## `__init__.py`

### 文件职责

该文件是 `src.utils` 包的公共入口，导出项目最常用的工具函数。

### 导出内容

- `clean_text`
- `json_log_record`
- `new_id`
- `parse_typed_id`
- `truncate_text`
- `utc_now`
- `utc_now_iso`

## `ids.py`

### 文件职责

该文件提供统一 ID 生成和解析逻辑。ID 格式为 `<prefix>-<random>`，其中 prefix 只能包含小写字母、数字和下划线。

### `_normalize_prefix(prefix: str) -> str`

清洗并校验 ID 前缀。

处理逻辑：
1. 去掉首尾空白并转成小写。
2. 如果结果为空，抛出 `ValueError`。
3. 如果不匹配 `^[a-z0-9_]+$`，抛出 `ValueError`。
4. 返回规范化后的 prefix。

### `new_id(prefix: str, *, size: int = 12) -> str`

生成带类型前缀的新 ID。

处理逻辑：
1. 调用 `_normalize_prefix` 校验 prefix。
2. `size <= 0` 时抛出 `ValueError`。
3. `size > 32` 时抛出 `ValueError`，因为 UUID hex 长度最多 32。
4. 调用 `uuid.uuid4().hex` 并截取前 `size` 位。
5. 返回 `<prefix>-<random>`。

### `event_id() -> str`

生成事件 ID。

行为：调用 `new_id("evt")`。

### `memory_id() -> str`

生成记忆 ID。

行为：调用 `new_id("mem")`。

### `query_id() -> str`

生成查询 ID。

行为：调用 `new_id("qry")`。

### `benchmark_run_id() -> str`

生成 benchmark run ID。

行为：调用 `new_id("bench")`。

### `request_id() -> str`

生成请求 ID。

行为：调用 `new_id("req")`。

### `parse_typed_id(value: str) -> tuple[str, str]`

解析 typed ID。

处理逻辑：
1. 去掉输入首尾空白。
2. 如果不包含 `-`，抛出 `ValueError`。
3. 按第一个 `-` 拆成 prefix 和 random part。
4. 调用 `_normalize_prefix` 校验 prefix。
5. 如果 random part 为空，抛出 `ValueError`。
6. 返回 `(prefix, random_part)`。

### `is_typed_id(value: str, prefix: str | None = None) -> bool`

判断字符串是否是合法 typed ID。

处理逻辑：
1. 调用 `parse_typed_id`。
2. 如果未传 `prefix`，解析成功即返回 `True`。
3. 如果传入 `prefix`，将它规范化后与解析出的 prefix 比较。
4. 任意解析或校验失败时返回 `False`。

## `jsonlog.py`

### 文件职责

该文件负责结构化 JSON 日志。它将常见 Python 对象安全转换为 JSON 可序列化结构，并避免业务字段覆盖日志保留字段。

### `json_safe(value: Any) -> Any`

将任意值转换为 JSON 友好的值。

处理规则：
- `None`、布尔、整数、浮点、字符串原样返回。
- `datetime` 调用 `format_iso` 转成 UTC ISO 字符串。
- `Enum` 返回 `.value`。
- dataclass 实例先转成 dict，再递归处理。
- dict 会把 key 转成字符串，并递归处理 value。
- list、tuple、set 会转成 list，并递归处理元素。
- 其他对象转成字符串。

### `json_dumps(data: Any) -> str`

安全输出 JSON 字符串。

处理逻辑：
1. 先调用 `json_safe(data)`。
2. 用 `json.dumps` 输出紧凑 JSON，`ensure_ascii=False` 保留中文。
3. 如果序列化仍失败，返回 `{"message":"<unserializable>"}`。

### `json_log_record(event: str, *, level: str = "INFO", message: str | None = None, **fields: Any) -> dict[str, Any]`

构造结构化日志记录。

处理流程：
1. 创建基础字段：`timestamp`、`level`、`event`、`message`。
2. `timestamp` 使用 `utc_now_iso()`。
3. `level` 转成大写。
4. 对额外字段调用 `json_safe`。
5. 跳过会覆盖保留字段的 key：`timestamp`、`level`、`event`、`message`。
6. 返回合并后的日志字典。

### `log_json(logger: logging.Logger, event: str, *, level: str = "INFO", message: str | None = None, **fields: Any) -> None`

向指定 logger 写入 JSON 日志。

处理逻辑：
1. 调用 `json_log_record` 构造日志字典。
2. 调用 `json_dumps` 转成字符串。
3. 根据 `level` 选择 logger 方法。
4. `warn` 会映射为 `warning`。
5. 非法级别 fallback 到 `info`。
6. 调用对应 logger 方法输出 JSON 字符串。

### `compact_dict(data: dict[str, Any], *, max_text_chars: int = 500) -> dict[str, Any]`

生成适合日志输出的紧凑字典。

处理逻辑：
1. 内部定义递归函数 `compact`。
2. 字符串调用 `safe_preview` 截断到 `max_text_chars`。
3. dict 递归处理 key 和 value。
4. list、tuple、set 转为 list 并递归处理。
5. 其他值调用 `json_safe`。
6. 返回新字典，不修改原始输入。

#### `compact(value: Any) -> Any`

`compact_dict` 内部递归函数。

该函数不对外导出，职责是按类型递归压缩字符串并转成 JSON 友好结构。

## `text.py`

### 文件职责

该文件提供文本规范化工具，避免控制字符、异常空白、超长文本和重复标签影响存储、日志和检索。

### `normalize_whitespace(text: str | None) -> str`

规范化空白字符。

处理逻辑：
1. 输入为空或 `None` 时返回空字符串。
2. 将连续空白替换成单个空格。
3. 去掉首尾空白。

### `clean_text(text: str | None, *, max_chars: int | None = None) -> str`

清洗文本。

处理逻辑：
1. 如果 `max_chars` 不为空且小于等于 0，抛出 `ValueError`。
2. 删除 ASCII 控制字符。
3. 调用 `normalize_whitespace` 规范化空白。
4. 如果传入 `max_chars`，调用 `truncate_text` 截断。
5. 返回清洗后的文本。

### `truncate_text(text: str | None, max_chars: int, *, suffix: str = "...") -> str`

截断文本。

处理逻辑：
1. `max_chars <= 0` 时抛出 `ValueError`。
2. `None` 输入按空字符串处理。
3. 文本长度不超过 `max_chars` 时原样返回。
4. 如果 `max_chars` 小于等于 suffix 长度，直接截取前 `max_chars` 个字符。
5. 否则截取可容纳 suffix 的前缀，并追加 suffix。

### `safe_preview(text: str | None, *, max_chars: int = 200) -> str`

生成安全预览文本。

行为：调用 `clean_text(text, max_chars=max_chars)`。

### `split_tags(value: str | list[str] | None) -> list[str]`

拆分并清洗标签。

处理逻辑：
1. `None` 返回空列表。
2. 字符串输入按分隔符正则拆分，列表输入直接使用。
3. 对每个 tag 调用 `normalize_whitespace`。
4. 空 tag 跳过。
5. 按小写 key 去重。
6. 保留首次出现的原始写法。

### `normalize_keyword(keyword: str | None) -> str`

规范化关键词。

行为：调用 `normalize_whitespace(keyword)` 后转小写。

### `contains_any(text: str | None, keywords: list[str] | tuple[str, ...], *, case_sensitive: bool = False) -> bool`

判断文本是否包含任意关键词。

处理逻辑：
1. 文本为空或关键词列表为空时返回 `False`。
2. 默认做大小写不敏感匹配。
3. 如果 `case_sensitive=True`，保留原大小写。
4. 跳过空关键词。
5. 任一关键词是文本子串时返回 `True`。
6. 全部未命中返回 `False`。

## `time.py`

### 文件职责

该文件统一处理 UTC 时间、ISO 字符串、时间窗口和过期判断，避免项目内混用 naive datetime 和本地时区。

### `utc_now() -> datetime`

返回当前 UTC 时间。

行为：调用 `datetime.now(timezone.utc)`，返回 aware datetime。

### `to_utc(dt: datetime) -> datetime`

将 datetime 转成 UTC aware datetime。

处理逻辑：
1. 如果 `dt.tzinfo is None`，按 UTC naive 处理，直接补 UTC 时区。
2. 如果已有时区，调用 `astimezone(timezone.utc)` 转成 UTC。

### `format_iso(dt: datetime | None = None) -> str`

格式化 UTC ISO 字符串。

处理逻辑：
1. 如果未传 `dt`，使用 `utc_now()`。
2. 调用 `to_utc` 转成 UTC。
3. 调用 `.isoformat()`。
4. 将 `+00:00` 替换为 `Z`。

### `utc_now_iso() -> str`

返回当前 UTC 时间的 ISO 字符串。

行为：调用 `format_iso(utc_now())`。

### `parse_iso(value: str) -> datetime`

解析 ISO 时间字符串。

处理逻辑：
1. 去掉首尾空白。
2. 空字符串抛出 `ValueError`。
3. 如果以 `Z` 结尾，转换为 `+00:00`。
4. 调用 `datetime.fromisoformat` 解析。
5. 调用 `to_utc` 返回 UTC aware datetime。
6. 解析失败时抛出带原始值的 `ValueError`。

### `_coerce_datetime(value: datetime | str) -> datetime`

将字符串或 datetime 统一转为 UTC datetime。

处理逻辑：
- datetime 输入调用 `to_utc`。
- 字符串输入调用 `parse_iso`。

### `add_duration(dt: datetime | str, **kwargs: int) -> datetime`

给时间增加一段 `timedelta`。

行为：先调用 `_coerce_datetime(dt)`，再加上 `timedelta(**kwargs)`。

### `time_window(reference: datetime | str | None = None, *, days: int = 0, hours: int = 0, minutes: int = 0) -> tuple[str, str]`

根据参考时间和持续时长生成时间窗口。

处理逻辑：
1. 如果 days、hours、minutes 都小于等于 0，抛出 `ValueError`。
2. `reference` 为空时使用 `utc_now()` 作为窗口结束时间。
3. `reference` 非空时调用 `_coerce_datetime` 作为结束时间。
4. 用结束时间减去 duration 得到开始时间。
5. 返回 `(start_iso, end_iso)`。

### `is_expired(valid_to: str | datetime | None, *, now: datetime | None = None) -> bool`

判断过期时间是否早于当前时间。

处理逻辑：
1. `valid_to is None` 时返回 `False`。
2. 调用 `_coerce_datetime` 转换 `valid_to`。
3. `now` 为空时使用 `utc_now()`。
4. 将 `now` 转成 UTC。
5. 如果 `valid_to_dt < now_dt`，返回 `True`，否则返回 `False`。

### `days_between(start: str | datetime, end: str | datetime | None = None) -> float`

计算两个时间之间相差的天数。

处理逻辑：
1. 调用 `_coerce_datetime` 转换 `start`。
2. `end` 为空时使用 `utc_now()`，否则调用 `_coerce_datetime(end)`。
3. 返回秒差除以 `86400`。
