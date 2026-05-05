from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(slots=True)
class AppSettings:
    app_name: str = "LarkMemory Engine"
    env: str = "local"
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False
    data_dir: str = ".larkmemory"
    sqlite_path: str = ".larkmemory/larkmemory.db"
    chroma_dir: str = ".larkmemory/chroma"
    chroma_collection: str = "memory_core"
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_timeout: float = 60.0
    llm_max_retries: int = 2
    llm_thinking_type: str | None = "disabled"
    enable_llm: bool = False
    enable_embedding: bool = False
    enable_vector_store: bool = False
    embedding_provider: str = "openai_compatible"
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_dimensions: int | None = None
    embedding_encoding_format: str = "float"
    embedding_model_path: str | None = None
    embedding_device: str = "cpu"
    embedding_normalize: bool = True
    embedding_batch_size: int = 4
    embedding_trust_remote_code: bool = True
    embedding_timeout: float = 60.0
    embedding_max_retries: int = 2
    enable_rerank: bool = False
    rerank_provider: str = "http"
    rerank_base_url: str | None = None
    rerank_endpoint_path: str = "/rerank"
    rerank_api_key: str | None = None
    rerank_model: str | None = None
    rerank_timeout: float = 60.0
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file: str = "larkmemory.log"
    request_log_enabled: bool = True
    enable_proactive_push: bool = False
    proactive_decider_min_confidence: float = 0.8
    proactive_related_top_k: int = 3


def _load_env_file(path: str | None) -> dict[str, str]:
    """读取 KEY=VALUE 文本配置文件；缺失文件返回空配置。"""
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _env_str(name: str, default: str | None, file_values: Mapping[str, str] | None = None) -> str | None:
    """按名称读取字符串配置；真实环境变量优先，其次配置文件，最后 default。"""
    value = os.getenv(name)
    if value is None and file_values is not None:
        value = file_values.get(name)
    if value is None:
        return default
    if value == "":
        return None
    return value


def _env_int(name: str, default: int, file_values: Mapping[str, str] | None = None) -> int:
    """按名称读取整数配置；缺失返回 default，格式非法时抛出带变量名的 ValueError。"""
    value = _env_str(name, None, file_values)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}: {value!r}") from exc


def _env_float(name: str, default: float, file_values: Mapping[str, str] | None = None) -> float:
    """按名称读取浮点配置；缺失返回 default，格式非法时抛出带变量名的 ValueError。"""
    value = _env_str(name, None, file_values)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {value!r}") from exc


def _env_bool(name: str, default: bool, file_values: Mapping[str, str] | None = None) -> bool:
    """按名称读取布尔配置；支持常见真假值，无法识别时抛出 ValueError。"""
    value = _env_str(name, None, file_values)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {name}: {value!r}")


def load_settings() -> AppSettings:
    """从配置文件和 `LARKMEMORY_*` 环境变量构建并返回 AppSettings。"""
    file_values = _load_env_file(os.getenv("LARKMEMORY_CONFIG_FILE", "larkmemory.env"))
    return AppSettings(
        app_name=_env_str("LARKMEMORY_APP_NAME", "LarkMemory Engine", file_values) or "LarkMemory Engine",
        env=_env_str("LARKMEMORY_ENV", "local", file_values) or "local",
        host=_env_str("LARKMEMORY_HOST", "127.0.0.1", file_values) or "127.0.0.1",
        port=_env_int("LARKMEMORY_PORT", 8765, file_values),
        debug=_env_bool("LARKMEMORY_DEBUG", False, file_values),
        data_dir=_env_str("LARKMEMORY_DATA_DIR", ".larkmemory", file_values) or ".larkmemory",
        sqlite_path=_env_str("LARKMEMORY_SQLITE_PATH", ".larkmemory/larkmemory.db", file_values)
        or ".larkmemory/larkmemory.db",
        chroma_dir=_env_str("LARKMEMORY_CHROMA_DIR", ".larkmemory/chroma", file_values)
        or ".larkmemory/chroma",
        chroma_collection=_env_str("LARKMEMORY_CHROMA_COLLECTION", "memory_core", file_values)
        or "memory_core",
        llm_api_key=_env_str("LARKMEMORY_LLM_API_KEY", None, file_values),
        llm_model=_env_str("LARKMEMORY_LLM_MODEL", None, file_values),
        llm_base_url=_env_str("LARKMEMORY_LLM_BASE_URL", None, file_values),
        llm_timeout=_env_float("LARKMEMORY_LLM_TIMEOUT", 60.0, file_values),
        llm_max_retries=_env_int("LARKMEMORY_LLM_MAX_RETRIES", 2, file_values),
        llm_thinking_type=_env_str("LARKMEMORY_LLM_THINKING_TYPE", "disabled", file_values),
        enable_llm=_env_bool("LARKMEMORY_ENABLE_LLM", False, file_values),
        enable_embedding=_env_bool("LARKMEMORY_ENABLE_EMBEDDING", False, file_values),
        enable_vector_store=_env_bool("LARKMEMORY_ENABLE_VECTOR_STORE", False, file_values),
        embedding_provider=_env_str("LARKMEMORY_EMBEDDING_PROVIDER", "openai_compatible", file_values)
        or "openai_compatible",
        embedding_api_key=_env_str("LARKMEMORY_EMBEDDING_API_KEY", None, file_values),
        embedding_model=_env_str("LARKMEMORY_EMBEDDING_MODEL", None, file_values),
        embedding_base_url=_env_str("LARKMEMORY_EMBEDDING_BASE_URL", None, file_values),
        embedding_dimensions=_env_int("LARKMEMORY_EMBEDDING_DIMENSIONS", 0, file_values) or None,
        embedding_encoding_format=_env_str("LARKMEMORY_EMBEDDING_ENCODING_FORMAT", "float", file_values)
        or "float",
        embedding_model_path=_env_str("LARKMEMORY_EMBEDDING_MODEL_PATH", None, file_values),
        embedding_device=_env_str("LARKMEMORY_EMBEDDING_DEVICE", "cpu", file_values) or "cpu",
        embedding_normalize=_env_bool("LARKMEMORY_EMBEDDING_NORMALIZE", True, file_values),
        embedding_batch_size=_env_int("LARKMEMORY_EMBEDDING_BATCH_SIZE", 4, file_values),
        embedding_trust_remote_code=_env_bool("LARKMEMORY_EMBEDDING_TRUST_REMOTE_CODE", True, file_values),
        embedding_timeout=_env_float("LARKMEMORY_EMBEDDING_TIMEOUT", 60.0, file_values),
        embedding_max_retries=_env_int("LARKMEMORY_EMBEDDING_MAX_RETRIES", 2, file_values),
        enable_rerank=_env_bool("LARKMEMORY_ENABLE_RERANK", False, file_values),
        rerank_provider=_env_str("LARKMEMORY_RERANK_PROVIDER", "http", file_values) or "http",
        rerank_base_url=_env_str("LARKMEMORY_RERANK_BASE_URL", None, file_values),
        rerank_endpoint_path=_env_str("LARKMEMORY_RERANK_ENDPOINT", "/rerank", file_values) or "/rerank",
        rerank_api_key=_env_str("LARKMEMORY_RERANK_API_KEY", None, file_values),
        rerank_model=_env_str("LARKMEMORY_RERANK_MODEL", None, file_values),
        rerank_timeout=_env_float("LARKMEMORY_RERANK_TIMEOUT", 60.0, file_values),
        log_level=_env_str("LARKMEMORY_LOG_LEVEL", "INFO", file_values) or "INFO",
        log_dir=_env_str("LARKMEMORY_LOG_DIR", "logs", file_values) or "logs",
        log_file=_env_str("LARKMEMORY_LOG_FILE", "larkmemory.log", file_values)
        or "larkmemory.log",
        request_log_enabled=_env_bool("LARKMEMORY_REQUEST_LOG_ENABLED", True, file_values),
        enable_proactive_push=_env_bool("LARKMEMORY_ENABLE_PROACTIVE_PUSH", False, file_values),
        proactive_decider_min_confidence=_env_float(
            "LARKMEMORY_PROACTIVE_DECIDER_MIN_CONFIDENCE",
            0.8,
            file_values,
        ),
        proactive_related_top_k=_env_int("LARKMEMORY_PROACTIVE_RELATED_TOP_K", 3, file_values),
    )


def build_llm_extra_body(settings: AppSettings) -> dict[str, object]:
    """构建 OpenAI-compatible LLM 请求附加体，用于模型厂商扩展参数。"""
    extra_body: dict[str, object] = {}
    if settings.llm_thinking_type:
        extra_body["thinking"] = {"type": settings.llm_thinking_type}
    return extra_body
