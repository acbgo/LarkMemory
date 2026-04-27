from __future__ import annotations

from functools import lru_cache

from src.app.config import AppSettings, load_settings
from src.core import MemoryService
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.llm import LLMClient
from src.storage import EmbeddingStore, EventStore, MemoryCoreStore, TeamRetentionStore


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return load_settings()


@lru_cache(maxsize=1)
def get_event_store() -> EventStore:
    store = EventStore(get_settings().sqlite_path)
    store.create_table()
    return store


@lru_cache(maxsize=1)
def get_memory_core_store() -> MemoryCoreStore:
    store = MemoryCoreStore(get_settings().sqlite_path)
    store.create_table()
    return store


@lru_cache(maxsize=1)
def get_team_retention_store() -> TeamRetentionStore:
    store = TeamRetentionStore(get_settings().sqlite_path)
    store.create_table()
    return store


@lru_cache(maxsize=1)
def get_embedding_store() -> EmbeddingStore | None:
    settings = get_settings()
    if not settings.enable_embedding:
        return None
    return EmbeddingStore(
        collection_name=settings.chroma_collection,
        persist_directory=settings.chroma_dir,
    )


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient | None:
    settings = get_settings()
    if not settings.enable_llm:
        return None
    if not settings.llm_api_key or not settings.llm_model:
        return None
    return LLMClient.from_openai_compatible(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries,
    )


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    return MemoryService(
        event_store=get_event_store(),
        memory_store=get_memory_core_store(),
        embedding_store=get_embedding_store(),
        llm_client=get_llm_client(),
        domain_handlers=[
            ProjectDecisionDomainHandler(
                get_memory_core_store(),
                llm_client=get_llm_client(),
            ),
            TeamRetentionDomainHandler(
                get_memory_core_store(),
                get_team_retention_store(),
                llm_client=get_llm_client(),
            ),
        ],
    )


def reset_dependency_cache() -> None:
    get_settings.cache_clear()
    get_event_store.cache_clear()
    get_memory_core_store.cache_clear()
    get_team_retention_store.cache_clear()
    get_embedding_store.cache_clear()
    get_llm_client.cache_clear()
    get_memory_service.cache_clear()
