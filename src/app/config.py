from __future__ import annotations

import os
from dataclasses import dataclass


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
    enable_llm: bool = False
    enable_embedding: bool = False
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


def _env_str(name: str, default: str | None) -> str | None:
    """按名称读取字符串环境变量；缺失返回 default，空字符串按显式 None 处理。"""
    value = os.getenv(name)
    if value is None:
        return default
    if value == "":
        return None
    return value


def _env_int(name: str, default: int) -> int:
    """按名称读取整数环境变量；缺失返回 default，格式非法时抛出带变量名的 ValueError。"""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}: {value!r}") from exc


def _env_float(name: str, default: float) -> float:
    """按名称读取浮点环境变量；缺失返回 default，格式非法时抛出带变量名的 ValueError。"""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {value!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    """按名称读取布尔环境变量；支持常见真假值，无法识别时抛出 ValueError。"""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean for {name}: {value!r}")


def load_settings() -> AppSettings:
    """从 `LARKMEMORY_*` 环境变量构建并返回 AppSettings 配置对象。"""
    return AppSettings(
        app_name=_env_str("LARKMEMORY_APP_NAME", "LarkMemory Engine") or "LarkMemory Engine",
        env=_env_str("LARKMEMORY_ENV", "local") or "local",
        host=_env_str("LARKMEMORY_HOST", "127.0.0.1") or "127.0.0.1",
        port=_env_int("LARKMEMORY_PORT", 8765),
        debug=_env_bool("LARKMEMORY_DEBUG", False),
        data_dir=_env_str("LARKMEMORY_DATA_DIR", ".larkmemory") or ".larkmemory",
        sqlite_path=_env_str("LARKMEMORY_SQLITE_PATH", ".larkmemory/larkmemory.db")
        or ".larkmemory/larkmemory.db",
        chroma_dir=_env_str("LARKMEMORY_CHROMA_DIR", ".larkmemory/chroma")
        or ".larkmemory/chroma",
        chroma_collection=_env_str("LARKMEMORY_CHROMA_COLLECTION", "memory_core")
        or "memory_core",
        llm_api_key=_env_str("LARKMEMORY_LLM_API_KEY", None),
        llm_model=_env_str("LARKMEMORY_LLM_MODEL", None),
        llm_base_url=_env_str("LARKMEMORY_LLM_BASE_URL", None),
        llm_timeout=_env_float("LARKMEMORY_LLM_TIMEOUT", 60.0),
        llm_max_retries=_env_int("LARKMEMORY_LLM_MAX_RETRIES", 2),
        enable_llm=_env_bool("LARKMEMORY_ENABLE_LLM", False),
        enable_embedding=_env_bool("LARKMEMORY_ENABLE_EMBEDDING", False),
        embedding_provider=_env_str("LARKMEMORY_EMBEDDING_PROVIDER", "openai_compatible")
        or "openai_compatible",
        embedding_api_key=_env_str("LARKMEMORY_EMBEDDING_API_KEY", None),
        embedding_model=_env_str("LARKMEMORY_EMBEDDING_MODEL", None),
        embedding_base_url=_env_str("LARKMEMORY_EMBEDDING_BASE_URL", None),
        embedding_dimensions=_env_int("LARKMEMORY_EMBEDDING_DIMENSIONS", 0) or None,
        embedding_encoding_format=_env_str("LARKMEMORY_EMBEDDING_ENCODING_FORMAT", "float")
        or "float",
        embedding_model_path=_env_str("LARKMEMORY_EMBEDDING_MODEL_PATH", None),
        embedding_device=_env_str("LARKMEMORY_EMBEDDING_DEVICE", "cpu") or "cpu",
        embedding_normalize=_env_bool("LARKMEMORY_EMBEDDING_NORMALIZE", True),
        embedding_batch_size=_env_int("LARKMEMORY_EMBEDDING_BATCH_SIZE", 4),
        embedding_trust_remote_code=_env_bool("LARKMEMORY_EMBEDDING_TRUST_REMOTE_CODE", True),
        embedding_timeout=_env_float("LARKMEMORY_EMBEDDING_TIMEOUT", 60.0),
        embedding_max_retries=_env_int("LARKMEMORY_EMBEDDING_MAX_RETRIES", 2),
        enable_rerank=_env_bool("LARKMEMORY_ENABLE_RERANK", False),
        rerank_provider=_env_str("LARKMEMORY_RERANK_PROVIDER", "http") or "http",
        rerank_base_url=_env_str("LARKMEMORY_RERANK_BASE_URL", None),
        rerank_endpoint_path=_env_str("LARKMEMORY_RERANK_ENDPOINT", "/rerank") or "/rerank",
        rerank_api_key=_env_str("LARKMEMORY_RERANK_API_KEY", None),
        rerank_model=_env_str("LARKMEMORY_RERANK_MODEL", None),
        rerank_timeout=_env_float("LARKMEMORY_RERANK_TIMEOUT", 60.0),
        log_level=_env_str("LARKMEMORY_LOG_LEVEL", "INFO") or "INFO",
        log_dir=_env_str("LARKMEMORY_LOG_DIR", "logs") or "logs",
        log_file=_env_str("LARKMEMORY_LOG_FILE", "larkmemory.log")
        or "larkmemory.log",
        request_log_enabled=_env_bool("LARKMEMORY_REQUEST_LOG_ENABLED", True),
    )
