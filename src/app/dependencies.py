from __future__ import annotations

import logging
from functools import lru_cache

from src.app.config import AppSettings, load_settings
from src.core import MemoryService
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.llm import (
    EmbeddingClient,
    LLMClient,
    LocalSentenceTransformersEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from src.storage import EmbeddingStore, EventStore, MemoryCoreStore, TeamRetentionStore


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """返回缓存的应用配置；首次调用会读取环境变量，后续复用同一 AppSettings 实例。"""
    return load_settings()


@lru_cache(maxsize=1)
def get_event_store() -> EventStore:
    """返回缓存的事件存储实例，使用当前配置中的 SQLite 路径。"""
    store = EventStore(get_settings().sqlite_path)
    store.create_table()
    return store


@lru_cache(maxsize=1)
def get_memory_core_store() -> MemoryCoreStore:
    """返回缓存的 MemoryCore 存储实例，使用当前配置中的 SQLite 路径。"""
    store = MemoryCoreStore(get_settings().sqlite_path)
    store.create_table()
    return store


@lru_cache(maxsize=1)
def get_team_retention_store() -> TeamRetentionStore:
    """返回缓存的团队留存存储实例，使用当前配置中的 SQLite 路径。"""
    store = TeamRetentionStore(get_settings().sqlite_path)
    store.create_table()
    return store


@lru_cache(maxsize=1)
def get_embedding_store() -> EmbeddingStore | None:
    """按配置返回缓存的向量存储实例；未启用嵌入时返回 None。"""
    settings = get_settings()
    if not settings.enable_embedding:
        return None
    return EmbeddingStore(
        collection_name=settings.chroma_collection,
        persist_directory=settings.chroma_dir,
    )


@lru_cache(maxsize=1)
def get_embedding_client() -> EmbeddingClient | None:
    """按配置返回缓存的 embedding client；未启用或配置缺失时返回 None。"""
    settings = get_settings()
    if not settings.enable_embedding:
        return None
    try:
        if settings.embedding_provider == "openai_compatible":
            if not settings.embedding_api_key or not settings.embedding_model:
                return None
            provider = OpenAICompatibleEmbeddingProvider(
                api_key=settings.embedding_api_key,
                model=settings.embedding_model,
                base_url=settings.embedding_base_url,
                dimensions=settings.embedding_dimensions,
                encoding_format=settings.embedding_encoding_format,
                timeout=settings.embedding_timeout,
                max_retries=settings.embedding_max_retries,
            )
        elif settings.embedding_provider in {"local", "local_sentence_transformers"}:
            if not settings.embedding_model_path:
                return None
            provider = LocalSentenceTransformersEmbeddingProvider(
                model_path=settings.embedding_model_path,
                device=settings.embedding_device,
                normalize_embeddings=settings.embedding_normalize,
                batch_size=settings.embedding_batch_size,
                dimensions=settings.embedding_dimensions,
                trust_remote_code=settings.embedding_trust_remote_code,
            )
        else:
            return None
    except Exception:
        logger.warning(
            "action=embedding_client_unavailable provider=%s",
            settings.embedding_provider,
            exc_info=True,
        )
        return None
    return EmbeddingClient(provider)


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient | None:
    """按配置返回缓存的 LLM 客户端；未启用或密钥/模型缺失时返回 None，不发起网络请求。"""
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
    """组装并返回缓存的 MemoryService，注入 store、LLM 和领域处理器依赖。"""
    return MemoryService(
        event_store=get_event_store(),
        memory_store=get_memory_core_store(),
        embedding_store=get_embedding_store(),
        embedding_client=get_embedding_client(),
        llm_client=get_llm_client(),
        domain_handlers=[
            ProjectDecisionDomainHandler(
                get_memory_core_store(),
                llm_client=get_llm_client(),
            ),
            TeamRetentionDomainHandler(
                get_memory_core_store(),
                get_team_retention_store(),
                embedding_store=get_embedding_store(),
                embedding_client=get_embedding_client(),
                llm_client=get_llm_client(),
            ),
        ],
    )


def reset_dependency_cache() -> None:
    """清空 app 依赖单例缓存，用于测试或环境变量变更后的重新加载。"""
    get_settings.cache_clear()
    get_event_store.cache_clear()
    get_memory_core_store.cache_clear()
    get_team_retention_store.cache_clear()
    get_embedding_store.cache_clear()
    get_embedding_client.cache_clear()
    get_llm_client.cache_clear()
    get_memory_service.cache_clear()
