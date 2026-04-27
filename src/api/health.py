from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.app.config import AppSettings
from src.app.dependencies import (
    get_embedding_store,
    get_event_store,
    get_llm_client,
    get_memory_core_store,
    get_settings,
)
from src.llm import LLMClient
from src.storage import EmbeddingStore, EventStore, MemoryCoreStore


router = APIRouter(tags=["health"])


def _check_store(store: EventStore | MemoryCoreStore) -> dict[str, Any]:
    """检查存储可用性并返回健康状态。"""
    try:
        store.fetch_one("SELECT 1 AS ok")
        return {"available": True}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


@router.get("/health")
def health_check(
    settings: AppSettings = Depends(get_settings),
    event_store: EventStore = Depends(get_event_store),
    memory_core_store: MemoryCoreStore = Depends(get_memory_core_store),
    embedding_store: EmbeddingStore | None = Depends(get_embedding_store),
    llm_client: LLMClient | None = Depends(get_llm_client),
) -> dict[str, Any]:
    """返回服务、存储、嵌入与 LLM 的健康信息。"""
    event_status = _check_store(event_store)
    memory_status = _check_store(memory_core_store)
    storage_available = event_status["available"] and memory_status["available"]

    return {
        "status": "ok" if storage_available else "degraded",
        "app": settings.app_name,
        "env": settings.env,
        "storage": {
            "event_store": event_status,
            "memory_core_store": memory_status,
        },
        "embedding": {
            "enabled": settings.enable_embedding,
            "available": embedding_store is not None,
        },
        "llm": {
            "enabled": settings.enable_llm,
            "available": llm_client is not None,
        },
    }
