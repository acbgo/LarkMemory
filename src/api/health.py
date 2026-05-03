from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from src.app.config import AppSettings
from src.app.dependencies import (
    get_embedding_client,
    get_embedding_store,
    get_event_store,
    get_llm_client,
    get_memory_core_store,
    get_settings,
)
from src.llm import LLMClient
from src.llm import EmbeddingClient
from src.storage import EmbeddingStore, EventStore, MemoryCoreStore


router = APIRouter(tags=["health"])


def _check_store(store: EventStore | MemoryCoreStore) -> dict[str, Any]:
    """检查 SQLite store 是否可查询，返回包含 available 和可选 error 的健康状态字典。"""
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
    embedding_client: EmbeddingClient | None = Depends(get_embedding_client),
    llm_client: LLMClient | None = Depends(get_llm_client),
) -> dict[str, Any]:
    """汇总配置、存储、嵌入和 LLM 可用性，返回 `/health` 接口响应字典。"""
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
            "available": embedding_store is not None and embedding_client is not None,
            "vector_store_available": embedding_store is not None,
            "embedding_client_available": embedding_client is not None,
            "provider": settings.embedding_provider if settings.enable_embedding else None,
            "model": (settings.embedding_model or settings.embedding_model_path)
            if settings.enable_embedding
            else None,
        },
        "llm": {
            "enabled": settings.enable_llm,
            "available": llm_client is not None,
        },
    }
