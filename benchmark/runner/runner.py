from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from pathlib import Path

from src.app.config import build_llm_extra_body, load_settings
from src.core.service import MemoryService
from src.domains.cli_workflow import CLIWorkflowDomainHandler
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.llm.client import LLMClient
from src.llm.embedding_client import EmbeddingClient
from src.llm.openai_compatible_embedding_provider import OpenAICompatibleEmbeddingProvider
from src.llm.rerank_client import RerankClient
from src.llm.http_rerank_provider import HttpRerankProvider
from src.retrieval._types import RetrievalQuery
from src.storage.base import SQLiteStore
from src.storage.cli_workflow_store import CLIWorkflowStore
from src.storage.embedding_store import EmbeddingStore
from src.storage.event_store import EventStore
from src.storage.memory_core_store import MemoryCoreStore
from src.storage.team_retention_store import TeamRetentionStore

from .adapter import convert_events
from .aggregator import aggregate
from .loader import load_cases
from .reporter import save_report
from .scorer import score_case
from .types import BenchmarkRunResult, CaseResult, RunnerConfig

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Isolated benchmark runner using temp SQLite DB per run."""

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config
        self._temp_dir: str | None = None
        self._db_path: str | None = None
        self._service: MemoryService | None = None
        self._event_store: EventStore | None = None
        self._memory_store: MemoryCoreStore | None = None
        self._cli_workflow_store: CLIWorkflowStore | None = None
        self._team_retention_store: TeamRetentionStore | None = None
        self._embedding_store: EmbeddingStore | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> BenchmarkRunResult:
        self._setup_isolation()

        try:
            cases = load_cases(
                datasets_dir=self.config.datasets_dir,
                suite_name=self.config.suite_name,
                case_ids=self.config.case_ids,
            )
            if not cases:
                raise RuntimeError(f"No cases loaded for suite '{self.config.suite_name}'")

            logger.info("Starting benchmark run %s with %d cases", self.config.run_id, len(cases))

            t0 = time.perf_counter()
            case_results: list[CaseResult] = []
            total = len(cases)
            for index, case in enumerate(cases, start=1):
                if self.config.progress_callback is not None:
                    self.config.progress_callback("case_start", index, total, case.case_id, None)
                cr = self._run_single_case(case)
                case_results.append(cr)
                if self.config.progress_callback is not None:
                    self.config.progress_callback("case_done", index, total, case.case_id, cr)

            duration = time.perf_counter() - t0

            result = aggregate(
                run_id=self.config.run_id,
                suite_name=self.config.suite_name,
                case_results=case_results,
                duration_seconds=duration,
            )

            logger.info(
                "Benchmark complete: overall=%.1f rating=%s passed=%d/%d errors=%d",
                result.overall_score,
                result.rating,
                result.passed_cases,
                result.total_cases,
                result.error_cases,
            )

            # Save reports if keep_temp
            if self.config.keep_temp and self._temp_dir:
                save_report(result, self._temp_dir)

            return result

        finally:
            if not self.config.keep_temp:
                self._cleanup()

    # ------------------------------------------------------------------
    # Isolation
    # ------------------------------------------------------------------

    def _setup_isolation(self) -> None:
        temp_root = Path(self.config.temp_root or "benchmark/.tmp-runs")
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_dir = temp_root / f"bench-{self.config.run_id}-{uuid.uuid4().hex[:8]}"
        temp_dir.mkdir(parents=True)
        self._temp_dir = str(temp_dir)
        self._db_path = str(Path(self._temp_dir) / "benchmark.db")

        # Load env file so LLM/Embedding/Rerank config is available
        _load_bench_env()

        self._event_store = EventStore(self._db_path)
        self._event_store.create_table()

        self._memory_store = MemoryCoreStore(self._db_path)
        self._memory_store.create_table()

        self._cli_workflow_store = CLIWorkflowStore(self._db_path)
        self._cli_workflow_store.create_table()

        # Team retention store (for knowledge_health / D direction)
        tr_db_path = str(Path(self._temp_dir) / "team_retention.db")
        self._team_retention_store = TeamRetentionStore(tr_db_path)
        self._team_retention_store.create_table()

        # Create LLM / Embedding / Rerank clients from env / config
        settings = load_settings()
        llm_client = self._create_llm_client()
        embedding_client = self._create_embedding_client()
        rerank_client = self._create_rerank_client()
        if settings.enable_embedding and settings.enable_vector_store:
            chroma_dir = str(Path(self._temp_dir) / "chroma")
            self._embedding_store = EmbeddingStore(
                collection_name=settings.chroma_collection,
                persist_directory=chroma_dir,
            )

        domain_handlers = [
            ProjectDecisionDomainHandler(
                self._memory_store,
                embedding_store=self._embedding_store,
                embedding_client=embedding_client,
                rerank_client=rerank_client,
                llm_client=llm_client,
            ),
            TeamRetentionDomainHandler(
                self._memory_store,
                self._team_retention_store,
                embedding_store=self._embedding_store,
                embedding_client=embedding_client,
                llm_client=llm_client,
            ),
            CLIWorkflowDomainHandler(
                self._memory_store,
                cli_store=self._cli_workflow_store,
                embedding_store=self._embedding_store,
                embedding_client=embedding_client,
                rerank_client=rerank_client,
                llm_client=llm_client,
            ),
        ]

        self._service = MemoryService(
            event_store=self._event_store,
            memory_store=self._memory_store,
            embedding_store=self._embedding_store,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            llm_client=llm_client,
            domain_handlers=domain_handlers,
        )
        logger.info(
            "Temp DB created at %s | llm=%s embedding=%s rerank=%s",
            self._db_path,
            llm_client is not None,
            embedding_client is not None,
            rerank_client is not None,
        )

    def _create_llm_client(self) -> LLMClient | None:
        """Create LLM client from config env vars, or None if not configured."""
        settings = load_settings()
        if not settings.enable_llm:
            return None
        if not settings.llm_api_key or not settings.llm_model:
            return None
        try:
            return LLMClient.from_openai_compatible(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout,
                max_retries=settings.llm_max_retries,
                extra_body=build_llm_extra_body(settings),
            )
        except Exception:
            logger.warning("Failed to create LLM client", exc_info=True)
            return None

    def _create_embedding_client(self) -> EmbeddingClient | None:
        """Create Embedding client from config env vars, or None if not configured."""
        settings = load_settings()
        if not settings.enable_embedding:
            return None
        if not settings.embedding_api_key or not settings.embedding_model:
            return None
        try:
            provider = OpenAICompatibleEmbeddingProvider(
                api_key=settings.embedding_api_key,
                model=settings.embedding_model,
                base_url=settings.embedding_base_url,
                dimensions=settings.embedding_dimensions,
                encoding_format=settings.embedding_encoding_format,
                timeout=settings.embedding_timeout,
                max_retries=settings.embedding_max_retries,
            )
            return EmbeddingClient(provider)
        except Exception:
            logger.warning("Failed to create embedding client", exc_info=True)
            return None

    def _create_rerank_client(self) -> RerankClient | None:
        """Create Rerank client from config env vars, or None if not configured."""
        settings = load_settings()
        if not settings.enable_rerank:
            return None
        if not settings.rerank_base_url:
            return None
        try:
            provider = HttpRerankProvider(
                base_url=settings.rerank_base_url,
                endpoint_path=settings.rerank_endpoint_path,
                model=settings.rerank_model,
                api_key=settings.rerank_api_key,
                timeout=settings.rerank_timeout,
            )
            return RerankClient(provider, model_name=settings.rerank_model or settings.rerank_base_url)
        except Exception:
            logger.warning("Failed to create rerank client", exc_info=True)
            return None

    def _cleanup(self) -> None:
        if self._temp_dir:
            try:
                shutil.rmtree(self._temp_dir)
                logger.info("Temp directory cleaned: %s", self._temp_dir)
            except Exception:
                logger.warning("Failed to clean temp dir: %s", self._temp_dir)

    # ------------------------------------------------------------------
    # Single case execution
    # ------------------------------------------------------------------

    def _reset_stores(self) -> None:
        """Clear all data between cases for clean isolation."""
        self._event_store.execute("DELETE FROM event_store")
        self._memory_store.execute("DELETE FROM memory_core")
        try:
            self._memory_store.execute("DELETE FROM memory_core_fts")
        except Exception:
            pass  # FTS may not exist if no data was inserted
        if self._cli_workflow_store is not None:
            self._cli_workflow_store.execute("DELETE FROM cli_command_pattern")
            self._cli_workflow_store.execute("DELETE FROM cli_parameter_policy")

    def _run_single_case(self, case) -> CaseResult:
        self._reset_stores()
        try:
            # Convert and sort events
            events = convert_events(case.input_events)

            # Ingest all events
            for evt in events:
                self._service.ingest_event(evt)

            # Build retrieval query
            query = RetrievalQuery(
                query_text=case.query,
                project_id=_extract_project_id(case),
                user_id=_extract_user_id(case),
            )

            # Retrieve
            retrieve_result = self._service.retrieve(query, top_k=10)

            # Score
            return score_case(case, retrieve_result.ranked_memories)

        except Exception as exc:
            logger.exception("Case %s failed", case.case_id)
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                test_type=case.test_type,
                difficulty=case.difficulty,
                error=str(exc)[:200],
            )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_project_id(case) -> str | None:
    # Allow expected block to specify the query project_id (for cross_project cases)
    exp = getattr(case, "expected", {}) or {}
    pid = exp.get("query_project_id")
    if pid:
        return pid
    for evt in case.input_events:
        ctx = evt.get("context", {})
        pid = ctx.get("project") or ctx.get("project_id")
        if pid:
            return pid
    return None


def _extract_user_id(case) -> str | None:
    for evt in case.input_events:
        uid = evt.get("speaker")
        if uid:
            return uid
        ctx = evt.get("context", {})
        uid = ctx.get("user") or ctx.get("user_id")
        if uid:
            return uid
    return None


# ------------------------------------------------------------------
# Env file loader (so LLM/Embedding/Rerank config is available to benchmarks)
# ------------------------------------------------------------------

def _load_bench_env() -> None:
    """Load larkmemory.env into os.environ for the benchmark runner."""
    env_path = Path("larkmemory.env")
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def _env_bool(name: str, default: bool) -> bool:
    """Read boolean from os.environ with fallback."""
    value = os.getenv(name)
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "ture"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default
