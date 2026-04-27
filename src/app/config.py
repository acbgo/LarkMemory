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
    log_level: str = "INFO"
    request_log_enabled: bool = True


def _env_str(name: str, default: str | None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    if value == "":
        return None
    return value


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {name}: {value!r}") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid float for {name}: {value!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
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
        log_level=_env_str("LARKMEMORY_LOG_LEVEL", "INFO") or "INFO",
        request_log_enabled=_env_bool("LARKMEMORY_REQUEST_LOG_ENABLED", True),
    )
