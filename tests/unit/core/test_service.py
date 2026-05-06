from __future__ import annotations

import asyncio
import shutil
import unittest
import uuid
from pathlib import Path

from src.core.memory_core import create_memory_core
from src.core.service import MemoryService
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.domains.team_retention.handler import TeamRetentionDomainHandler
from src.retrieval import RankedMemory, RetrievalQuery, memory_item_from_core
from src.schemas import EventContext, NormalizedEvent
from src.storage import EventStore, MemoryCoreStore, TeamRetentionStore


class FakeIngestLLM:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    async def atext(
        self,
        system_prompt: str | None,
        user_prompt: str,
        **kwargs: object,
    ) -> str:
        self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        if not self.payloads:
            raise AssertionError("unexpected LLM call")
        first = self.payloads.pop(0)
        return str(first.get("domain", "team_retention"))

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        if not self.payloads:
            raise AssertionError("unexpected LLM call")
        return self.payloads.pop(0)


class FakeRetrieveLLM:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)

    async def atext(
        self,
        system_prompt: str | None,
        user_prompt: str,
        **kwargs: object,
    ) -> str:
        if not self.texts:
            raise AssertionError("unexpected LLM call")
        return self.texts.pop(0)


class FakeRetrieveJudgeLLM:
    def __init__(self, texts: list[str], payloads: list[dict[str, object] | BaseException]) -> None:
        self.texts = list(texts)
        self.payloads = list(payloads)
        self.calls: list[dict[str, object]] = []

    async def atext(
        self,
        system_prompt: str | None,
        user_prompt: str,
        **kwargs: object,
    ) -> str:
        self.calls.append({"method": "atext", "system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        if not self.texts:
            raise AssertionError("unexpected LLM text call")
        return self.texts.pop(0)

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"method": "ajson", "system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        if "primary" in (kwargs.get("schema") or {}).get("required", []):
            return {"primary": "project_decision", "confidence": 0.9, "reason": "测试分类"}
        if not self.payloads:
            raise AssertionError("unexpected LLM json call")
        payload = self.payloads.pop(0)
        if isinstance(payload, BaseException):
            raise payload
        return payload


class SpyRetrieveHandler:
    def __init__(self, domain: str = "project_decision", rows: list[object] | None = None) -> None:
        self.domain = domain
        self.queries: list[RetrievalQuery] = []
        self.rows = list(rows or [])

    def ingest_event(self, event: NormalizedEvent, runtime: object) -> object:
        raise AssertionError("not used")

    def retrieve(self, query: RetrievalQuery, *, top_k: int) -> list[object]:
        self.queries.append(query)
        return [
            RankedMemory(item=memory_item_from_core(row), final_score=1.0, rank=index + 1)
            for index, row in enumerate(self.rows[:top_k])
        ]

    def update_memory(self, action: str, **kwargs: object) -> object | None:
        return None

    def proactive_suggestions(self, **kwargs: object) -> list[dict[str, object]]:
        return []

    def scan_review_due(self, **kwargs: object) -> list[dict[str, object]]:
        return []


class FakeProactiveEngine:
    def __init__(self, *, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls: list[dict[str, object]] = []

    def maybe_push(self, event: NormalizedEvent, *, domain: str | None, memory_ids: list[str]) -> None:
        self.calls.append({"event_id": event.event_id, "domain": domain, "memory_ids": list(memory_ids)})
        if self.should_raise:
            raise RuntimeError("proactive failed")


class FakeGlobalRerankClient:
    def __init__(self, ordered_ids: list[str], *, score: float | None = None) -> None:
        self.ordered_ids = ordered_ids
        self.score = score
        self.calls: list[dict[str, object]] = []

    def rerank(self, query: str, documents: list[object], *, top_k: int | None = None) -> object:
        self.calls.append({"query": query, "documents": documents, "top_k": top_k})
        result_by_id = {getattr(document, "id"): document for document in documents}
        results = []
        for rank, memory_id in enumerate(self.ordered_ids[: top_k or len(self.ordered_ids)], start=1):
            document = result_by_id[memory_id]
            results.append(
                type(
                    "FakeRerankResult",
                    (),
                    {
                        "id": memory_id,
                        "score": self.score if self.score is not None else float(100 - rank),
                        "rank": rank,
                        "index": rank - 1,
                        "metadata": getattr(document, "metadata", {}),
                    },
                )()
            )
        return type("FakeRerankResponse", (), {"model": "fake-rerank", "results": results})()


class TestService(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"core-service-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.event_store = EventStore(str(self.temp_dir / "events.db"))
        self.event_store.create_table()
        self.memory_store = MemoryCoreStore(str(self.temp_dir / "memory.db"))
        self.memory_store.create_table()
        self.team_retention_store = TeamRetentionStore(str(self.temp_dir / "memory.db"))
        self.team_retention_store.create_table()
        self.service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[
                ProjectDecisionDomainHandler(self.memory_store),
                TeamRetentionDomainHandler(self.memory_store, self.team_retention_store),
            ],
        )

    def test_ingest_event_writes_event_store(self) -> None:
        event = NormalizedEvent(
            event_id="event-1",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(),
            content_text="决定采用方案 B",
        )

        result = self.service.ingest_event(event)

        self.assertTrue(result.stored)
        self.assertIsNotNone(self.event_store.get_event("event-1"))
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(len(result.memory_ids), 1)
        self.assertIsNotNone(self.memory_store.get_memory(result.memory_ids[0]))

    def test_llm_memory_gate_can_skip_extraction(self) -> None:
        llm = FakeIngestLLM(
            [
                {
                    "domain": "project_decision",
                },
                {
                    "should_extract": False,
                }
            ]
        )
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            llm_client=llm,
            domain_handlers=[ProjectDecisionDomainHandler(self.memory_store, llm_client=llm)],
        )
        event = NormalizedEvent(
            event_id="event-llm-skip",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(project_id="project-1"),
            content_text="收到，下午见",
        )

        result = service.ingest_event(event)

        self.assertTrue(result.stored)
        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.memory_ids, [])
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("admission rejected", result.message or "")

    def test_llm_ingest_routes_extracts_and_stores_project_decision(self) -> None:
        llm = FakeIngestLLM(
            [
                {
                    "domain": "project_decision",
                },
                {
                    "should_extract": True,
                },
                {
                    "memories": [
                        {
                            "topic": "storage choice",
                            "content": "use SQLite for local demo",
                            "confidence": 0.9,
                        }
                    ],
                },
            ]
        )
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            llm_client=llm,
            domain_handlers=[ProjectDecisionDomainHandler(self.memory_store, llm_client=llm)],
        )
        event = NormalizedEvent(
            event_id="event-llm-project",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(project_id="project-1"),
            content_text="team aligned on SQLite for the local demo",
        )

        with self.assertLogs(level="INFO") as captured:
            result = service.ingest_event(event)

        logs = "\n".join(captured.output)
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(len(result.memory_ids), 1)
        row = self.memory_store.get_memory(result.memory_ids[0])
        self.assertEqual(row["domain"], "project_decision")
        self.assertIn("use SQLite for local demo", row["content_text"])
        self.assertEqual(len(llm.calls), 3)
        self.assertIn("action=llm_memory_gate", logs)
        self.assertIn("project_decision", logs)
        self.assertIn("action=done event_id=event-llm-project candidate_count=1", logs)
        self.assertIn("action=stored event_id=event-llm-project", logs)

    def test_ingest_event_emits_action_level_logs(self) -> None:
        event = NormalizedEvent(
            event_id="event-log",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(project_id="project-log"),
            content_text="decision confirmed choose plan B because it is safer",
        )

        with self.assertLogs(level="INFO") as captured:
            result = self.service.ingest_event(event)

        logs = "\n".join(captured.output)
        self.assertEqual(result.candidate_count, 1)
        self.assertIn("action=start event_id=event-log", logs)
        self.assertIn("action=inserted event_id=event-log", logs)
        self.assertIn("primary_domain=project_decision", logs)
        self.assertIn(
            "action=done event_id=event-log raw_candidate_count=",
            logs,
        )
        self.assertIn(
            "action=done decision_id=",
            logs,
        )
        self.assertIn(
            "action=inserted memory_id=",
            logs,
        )

    def test_ingest_event_supersedes_old_project_decision(self) -> None:
        first = NormalizedEvent(
            event_id="event-old",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(project_id="project-1"),
            content_text="确认截止日期是 5 号",
        )
        second = NormalizedEvent(
            event_id="event-new",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-28T00:00:00Z",
            context=EventContext(project_id="project-1"),
            content_text="确认截止日期改为 8 号",
        )

        old_id = self.service.ingest_event(first).memory_ids[0]
        new_id = self.service.ingest_event(second).memory_ids[0]

        old_row = self.memory_store.get_memory(old_id)
        new_row = self.memory_store.get_memory(new_id)
        self.assertEqual(old_row["status"], "superseded")
        self.assertEqual(old_row["superseded_by"], new_id)
        self.assertEqual(new_row["overwrite_of"], old_id)

    def test_add_memory_and_duplicate(self) -> None:
        memory = create_memory_core(
            memory_id="mem-1",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-1",
            content_text="Use SQLite",
            entities=["project_id:project-1"],
            importance=0.9,
            confidence=0.9,
            status="active",
        )
        duplicate = create_memory_core(
            memory_id="mem-2",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-2",
            content_text="Use SQLite",
            entities=["project_id:project-1"],
            importance=0.9,
            confidence=0.9,
            status="active",
        )

        self.assertEqual(self.service.add_memory(memory), "mem-1")
        self.assertEqual(self.service.add_memory(duplicate), "mem-1")

    def test_add_memory_does_not_deduplicate_across_project_scope(self) -> None:
        first = create_memory_core(
            memory_id="mem-project-1",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project-1",
            content_text="Use SQLite",
            entities=["project_id:project-1"],
            status="active",
        )
        second = create_memory_core(
            memory_id="mem-project-2",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project-2",
            content_text="Use SQLite",
            entities=["project_id:project-2"],
            status="active",
        )

        self.assertEqual(self.service.add_memory(first), "mem-project-1")
        self.assertEqual(self.service.add_memory(second), "mem-project-2")
        self.assertIsNotNone(self.memory_store.get_memory("mem-project-2"))

    def test_add_memory_overwrite_of_skips_duplicate_check(self) -> None:
        old = create_memory_core(
            memory_id="mem-old-version",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-old-version",
            content_text="Use SQLite",
            entities=["project_id:project-1"],
            status="active",
        )
        new = create_memory_core(
            memory_id="mem-new-version",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-new-version",
            content_text="Use SQLite",
            entities=["project_id:project-1"],
            status="active",
        )
        new.overwrite_of = "mem-old-version"

        self.assertEqual(self.service.add_memory(old), "mem-old-version")
        self.assertEqual(self.service.add_memory(new), "mem-new-version")
        self.assertEqual(self.memory_store.get_memory("mem-new-version")["overwrite_of"], "mem-old-version")

    def test_add_memory_candidate_participates_in_scoped_duplicate_check(self) -> None:
        candidate = create_memory_core(
            memory_id="mem-candidate",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-candidate",
            content_text="Use SQLite",
            entities=["workspace_id:workspace-1"],
            status="candidate",
        )
        duplicate = create_memory_core(
            memory_id="mem-candidate-duplicate",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-candidate-duplicate",
            content_text="Use SQLite",
            entities=["workspace_id:workspace-1"],
            status="active",
        )

        self.assertEqual(self.service.add_memory(candidate), "mem-candidate")
        self.assertEqual(self.service.add_memory(duplicate), "mem-candidate")

    def test_retrieve_empty_and_with_memory(self) -> None:
        empty = self.service.retrieve(RetrievalQuery("sqlite"), include_trace=True)
        self.assertEqual(empty.ranked_memories, [])
        self.assertEqual(empty.trace["mode"], "memory_core_fallback")

        self.memory_store.insert_memory_core(
            create_memory_core(
                memory_id="mem-1",
                domain="project_decision",
                memory_type="decision",
                scope="project",
                source_type="feishu_chat",
                source_ref="event-1",
                content_text="Use SQLite",
                importance=0.9,
                confidence=0.9,
                status="active",
            )
        )
        result = self.service.retrieve(RetrievalQuery("sqlite"), top_k=1)

        self.assertEqual(len(result.ranked_memories), 1)
        self.assertEqual(result.ranked_memories[0].item.memory_id, "mem-1")

    def test_retrieve_async_supports_existing_event_loop(self) -> None:
        self.memory_store.insert_memory_core(
            create_memory_core(
                memory_id="mem-async",
                domain="project_decision",
                memory_type="decision",
                scope="project",
                source_type="feishu_chat",
                source_ref="event-async",
                content_text="Use async retrieval for FastAPI",
                importance=0.9,
                confidence=0.9,
                status="active",
            )
        )

        async def run_retrieve() -> str:
            """在已有事件循环中调用异步检索入口，验证不会触发同步包装器异常。"""
            result = await self.service.retrieve_async(RetrievalQuery("async retrieval"), top_k=1)
            return result.ranked_memories[0].item.memory_id

        self.assertEqual(asyncio.run(run_retrieve()), "mem-async")

    def test_retrieve_passes_rewritten_query_variants_to_domain_handler(self) -> None:
        handler = SpyRetrieveHandler()
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            llm_client=FakeRetrieveLLM(["project_decision", "查询项目中为什么选择方案 B 的历史决策和理由"]),
            domain_handlers=[handler],  # type: ignore[list-item]
        )

        service.retrieve(RetrievalQuery("为什么选方案B", project_id="project-1"), top_k=1)

        self.assertEqual(len(handler.queries), 1)
        self.assertEqual(
            handler.queries[0].session_context["query_variants"],
            ["为什么选方案B", "查询项目中为什么选择方案 B 的历史决策和理由"],
        )
        self.assertEqual(
            handler.queries[0].session_context["rewritten_text"],
            "查询项目中为什么选择方案 B 的历史决策和理由",
        )

    def test_retrieve_does_not_query_secondary_when_primary_returns_results(self) -> None:
        project_memory = create_memory_core(
            memory_id="mem-project",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project",
            content_text="采用 SQLite",
            summary_text="采用 SQLite",
        )
        primary = SpyRetrieveHandler("project_decision", [project_memory])
        secondary = SpyRetrieveHandler("team_retention")
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[primary, secondary],  # type: ignore[list-item]
        )

        result = service.retrieve(RetrievalQuery("为什么选择 SQLite", project_id="project-1"), top_k=1, include_trace=True)

        self.assertEqual([memory.item.memory_id for memory in result.ranked_memories], ["mem-project"])
        self.assertEqual(len(primary.queries), 1)
        self.assertEqual(secondary.queries, [])
        self.assertEqual(result.trace["target_domains"], ["project_decision"])

    def test_retrieve_uses_secondary_only_when_primary_empty(self) -> None:
        secondary_memory = create_memory_core(
            memory_id="mem-team",
            domain="team_retention",
            memory_type="team_retention",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-team",
            content_text="团队长期记住 API key 轮换",
            summary_text="API key 轮换",
        )
        primary = SpyRetrieveHandler("project_decision")
        secondary = SpyRetrieveHandler("team_retention", [secondary_memory])
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[primary, secondary],  # type: ignore[list-item]
        )

        result = service.retrieve(RetrievalQuery("为什么选择 SQLite", project_id="project-1"), top_k=1, include_trace=True)

        self.assertEqual([memory.item.memory_id for memory in result.ranked_memories], ["mem-team"])
        self.assertEqual(len(primary.queries), 1)
        self.assertEqual(len(secondary.queries), 1)
        self.assertEqual(result.trace["target_domains"], ["project_decision", "team_retention"])

    def test_retrieve_uses_global_rerank_client_when_configured(self) -> None:
        project_memory = create_memory_core(
            memory_id="mem-project",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project",
            content_text="SQLite 决策",
            summary_text="SQLite 决策",
        )
        team_memory = create_memory_core(
            memory_id="mem-team",
            domain="team_retention",
            memory_type="team_retention",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-team",
            content_text="会议室外卖规则",
            summary_text="会议室外卖规则",
        )
        handler = SpyRetrieveHandler("project_decision", [team_memory, project_memory])
        rerank_client = FakeGlobalRerankClient(["mem-project", "mem-team"])
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[handler],  # type: ignore[list-item]
            rerank_client=rerank_client,
        )

        with self.assertLogs("src.core.service", level="INFO") as captured:
            result = service.retrieve(RetrievalQuery("SQLite 数据库选型理由", project_id="project-1"), top_k=2)

        self.assertEqual([memory.item.memory_id for memory in result.ranked_memories], ["mem-project", "mem-team"])
        self.assertEqual(len(rerank_client.calls), 1)
        logs = "\n".join(captured.output)
        self.assertIn("action=global_rerank_done", logs)
        self.assertIn("raw_scores=", logs)
        self.assertIn("top_ids=['mem-project', 'mem-team']", logs)

    def test_retrieve_filters_irrelevant_candidates_before_rerank(self) -> None:
        project_memory = create_memory_core(
            memory_id="mem-project",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project",
            content_text="SQLite 数据库选型决策",
            summary_text="SQLite 数据库选型决策",
        )
        noise_memory = create_memory_core(
            memory_id="mem-noise",
            domain="team_retention",
            memory_type="team_fact",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-noise",
            content_text="报销单据应统一贴在 A4 纸上",
            summary_text="报销规则",
        )
        related_memory = create_memory_core(
            memory_id="mem-related",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-related",
            content_text="生产环境数据库后续再评估 PostgreSQL",
            summary_text="数据库后续评估",
        )
        handler = SpyRetrieveHandler("project_decision", [noise_memory, project_memory, related_memory])
        llm = FakeRetrieveJudgeLLM(
            ["project_decision", "SQLite 数据库选型理由"],
            [
                {
                    "results": [
                        {"id": "mem-noise", "relevant": False, "confidence": 0.95, "reason": "报销规则与数据库选型无关"},
                        {"id": "mem-project", "relevant": True, "confidence": 0.9, "reason": "直接回答数据库选型"},
                        {"id": "mem-related", "relevant": True, "confidence": 0.8, "reason": "相关数据库背景"},
                    ]
                }
            ],
        )
        rerank_client = FakeGlobalRerankClient(["mem-project", "mem-related"])
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            llm_client=llm,
            domain_handlers=[handler],  # type: ignore[list-item]
            rerank_client=rerank_client,
        )

        result = service.retrieve(RetrievalQuery("SQLite 数据库选型理由", project_id="project-1"), top_k=3, include_trace=True)

        self.assertEqual([memory.item.memory_id for memory in result.ranked_memories], ["mem-project", "mem-related"])
        self.assertEqual([getattr(document, "id") for document in rerank_client.calls[0]["documents"]], ["mem-project", "mem-related"])
        self.assertEqual(result.trace["candidate_count"], 3)
        self.assertEqual(result.trace["filtered_candidate_count"], 2)

    def test_retrieve_keeps_candidates_when_llm_relevance_filter_fails(self) -> None:
        project_memory = create_memory_core(
            memory_id="mem-project",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project",
            content_text="SQLite 数据库选型决策",
            summary_text="SQLite 数据库选型决策",
        )
        noise_memory = create_memory_core(
            memory_id="mem-noise",
            domain="team_retention",
            memory_type="team_fact",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-noise",
            content_text="报销单据应统一贴在 A4 纸上",
            summary_text="报销规则",
        )
        handler = SpyRetrieveHandler("project_decision", [noise_memory, project_memory])
        llm = FakeRetrieveJudgeLLM(
            ["project_decision", "SQLite 数据库选型理由"],
            [RuntimeError("judge unavailable")],
        )
        rerank_client = FakeGlobalRerankClient(["mem-project", "mem-noise"])
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            llm_client=llm,
            domain_handlers=[handler],  # type: ignore[list-item]
            rerank_client=rerank_client,
        )

        result = service.retrieve(RetrievalQuery("SQLite 数据库选型理由", project_id="project-1"), top_k=2, include_trace=True)

        self.assertEqual([memory.item.memory_id for memory in result.ranked_memories], ["mem-project", "mem-noise"])
        self.assertEqual(len(rerank_client.calls[0]["documents"]), 2)
        self.assertEqual(result.trace["filtered_candidate_count"], 2)
        self.assertTrue(result.trace["llm_relevance_filter"]["failed"])

    def test_retrieve_returns_empty_when_all_candidates_are_irrelevant(self) -> None:
        noise_memory = create_memory_core(
            memory_id="mem-noise",
            domain="team_retention",
            memory_type="team_fact",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-noise",
            content_text="报销单据应统一贴在 A4 纸上",
            summary_text="报销规则",
        )
        handler = SpyRetrieveHandler("project_decision", [noise_memory])
        llm = FakeRetrieveJudgeLLM(
            ["project_decision", "SQLite 数据库选型理由"],
            [
                {
                    "results": [
                        {"id": "mem-noise", "relevant": False, "confidence": 0.95, "reason": "无关"}
                    ]
                }
            ],
        )
        rerank_client = FakeGlobalRerankClient(["mem-noise"])
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            llm_client=llm,
            domain_handlers=[handler],  # type: ignore[list-item]
            rerank_client=rerank_client,
        )

        result = service.retrieve(RetrievalQuery("SQLite 数据库选型理由", project_id="project-1"), top_k=1, include_trace=True)

        self.assertEqual(result.ranked_memories, [])
        self.assertEqual(rerank_client.calls, [])
        self.assertEqual(result.trace["candidate_count"], 1)
        self.assertEqual(result.trace["filtered_candidate_count"], 0)

    def test_retrieve_falls_back_to_local_rerank_when_global_rerank_scores_are_all_zero(self) -> None:
        project_memory = create_memory_core(
            memory_id="mem-project",
            domain="project_decision",
            memory_type="decision",
            scope="project",
            source_type="feishu_chat",
            source_ref="event-project",
            content_text="SQLite 决策",
            summary_text="SQLite 决策",
        )
        team_memory = create_memory_core(
            memory_id="mem-team",
            domain="team_retention",
            memory_type="team_retention",
            scope="team",
            source_type="feishu_chat",
            source_ref="event-team",
            content_text="会议室外卖规则",
            summary_text="会议室外卖规则",
        )
        handler = SpyRetrieveHandler("project_decision", [team_memory, project_memory])
        rerank_client = FakeGlobalRerankClient(["mem-team", "mem-project"], score=0.0)
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[handler],  # type: ignore[list-item]
            rerank_client=rerank_client,
        )

        with self.assertLogs("src.core.service", level="INFO") as captured:
            result = service.retrieve(RetrievalQuery("SQLite 数据库选型理由", project_id="project-1"), top_k=2)

        self.assertEqual(len(result.ranked_memories), 2)
        self.assertTrue(all(memory.final_score > 0 for memory in result.ranked_memories))
        logs = "\n".join(captured.output)
        self.assertIn("action=global_rerank_zero_scores", logs)

    def test_retrieve_emits_clear_pipeline_logs(self) -> None:
        self.memory_store.insert_memory_core(
            create_memory_core(
                memory_id="mem-log",
                domain="project_decision",
                memory_type="decision",
                scope="project",
                source_type="feishu_chat",
                source_ref="event-log",
                content_text="Use SQLite for local memory storage",
                importance=0.9,
                confidence=0.9,
                status="active",
            )
        )

        with self.assertLogs(level="INFO") as captured:
            result = self.service.retrieve(RetrievalQuery("SQLite"), top_k=1)

        logs = "\n".join(captured.output)
        self.assertEqual(len(result.ranked_memories), 1)
        self.assertIn("action=retrieve_start", logs)
        self.assertIn("action=domain_retrieve_start domain=project_decision", logs)
        self.assertIn("action=rerank_start", logs)
        self.assertNotIn("function=src.core.service.MemoryService.retrieve_async", logs)
        self.assertNotIn("function=src.retrieval.rerank.Reranker.rerank", logs)

    def test_update_actions(self) -> None:
        for memory_id, text in [("mem-old", "old"), ("mem-new", "new"), ("mem-score", "score")]:
            self.memory_store.insert_memory_core(
                create_memory_core(
                    memory_id=memory_id,
                    domain="project_decision",
                    memory_type="decision",
                    scope="project",
                    source_type="feishu_chat",
                    source_ref=f"event-{memory_id}",
                    content_text=text,
                    status="active",
                )
            )

        self.assertTrue(self.service.update_memory("expire", memory_id="mem-score").updated)
        self.assertEqual(self.memory_store.get_memory("mem-score")["status"], "expired")
        self.assertTrue(self.service.update_memory("supersede", memory_id="mem-old", new_memory_id="mem-new").updated)
        self.assertEqual(self.memory_store.get_memory("mem-old")["status"], "superseded")
        self.assertTrue(self.service.update_memory("confidence", memory_id="mem-new", confidence=0.7).updated)
        self.assertTrue(self.service.update_memory("importance", memory_id="mem-new", importance=0.8).updated)
        feedback = self.service.update_memory("feedback", memory_id="mem-new", feedback_signal="useful")
        self.assertFalse(feedback.updated)

    def test_proactive_and_maintenance(self) -> None:
        self.assertEqual(self.service.proactive_suggestions(), [])
        self.assertIn("decay", self.service.run_maintenance())

    def test_ingest_event_triggers_proactive_engine_after_domain_ingest(self) -> None:
        proactive_engine = FakeProactiveEngine()
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            proactive_engine=proactive_engine,
            domain_handlers=[ProjectDecisionDomainHandler(self.memory_store)],
        )
        event = NormalizedEvent(
            event_id="event-proactive",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-05-05T00:00:00Z",
            context=EventContext(project_id="project-1", team_id="team-1", workspace_id="workspace-1"),
            content_text="决定采用方案 B，而不是方案 A",
            payload={"chat_id": "oc_chat_1"},
        )

        result = service.ingest_event(event)

        self.assertEqual(len(result.memory_ids), 1)
        self.assertEqual(proactive_engine.calls, [{"event_id": "event-proactive", "domain": "project_decision", "memory_ids": result.memory_ids}])

    def test_ingest_event_ignores_proactive_engine_failure(self) -> None:
        proactive_engine = FakeProactiveEngine(should_raise=True)
        service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            proactive_engine=proactive_engine,
            domain_handlers=[ProjectDecisionDomainHandler(self.memory_store)],
        )
        event = NormalizedEvent(
            event_id="event-proactive-fail",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-05-05T00:00:00Z",
            context=EventContext(project_id="project-1", team_id="team-1", workspace_id="workspace-1"),
            content_text="决定采用方案 B，而不是方案 A",
            payload={"chat_id": "oc_chat_1"},
        )

        result = service.ingest_event(event)

        self.assertTrue(result.stored)
        self.assertEqual(len(result.memory_ids), 1)

    def test_ingest_team_retention_creates_memory_and_review_schedule(self) -> None:
        event = NormalizedEvent(
            event_id="event-retention",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：客户 A 要求所有导出文件使用 xlsx，不接受 csv。",
        )

        result = self.service.ingest_event(event)
        memory_id = result.memory_ids[0]

        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(self.memory_store.get_memory(memory_id)["domain"], "team_retention")
        self.assertIsNotNone(self.team_retention_store.get_memory(memory_id))
        self.assertIsNotNone(self.team_retention_store.get_review_schedule(memory_id))

    def test_team_retention_proactive_review_and_reviewed_update(self) -> None:
        event = NormalizedEvent(
            event_id="event-retention-due",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：API key 已更新到 secret-v2，旧 key 不再使用。",
        )
        memory_id = self.service.ingest_event(event).memory_ids[0]

        suggestions = self.service.proactive_suggestions(
            team_id="team-1",
            now="2026-04-28T00:00:00Z",
        )
        update = self.service.update_memory(
            "reviewed",
            memory_id=memory_id,
            reviewed_at="2026-04-28T00:00:00Z",
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["memory_id"], memory_id)
        self.assertTrue(update.updated)
        self.assertIn("next_review_at=", update.message)

    def test_team_retention_supersedes_old_version(self) -> None:
        first = NormalizedEvent(
            event_id="event-retention-old",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：客户 A 要求所有导出文件使用 xlsx，不接受 csv。",
            payload={"version_group": "team-1:customer-a-export"},
        )
        second = NormalizedEvent(
            event_id="event-retention-new",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-28T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：客户 A 现在接受 csv，但必须 UTF-8 编码。",
            payload={"version_group": "team-1:customer-a-export"},
        )

        old_id = self.service.ingest_event(first).memory_ids[0]
        new_id = self.service.ingest_event(second).memory_ids[0]

        self.assertEqual(self.memory_store.get_memory(old_id)["status"], "superseded")
        self.assertEqual(self.memory_store.get_memory(old_id)["superseded_by"], new_id)
        self.assertFalse(self.team_retention_store.get_review_schedule(old_id).active)

    def test_team_retention_retrieve_without_scope_returns_empty_no_fallback(self) -> None:
        event = NormalizedEvent(
            event_id="event-retention-scope",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：客户 A 要求所有导出文件使用 xlsx。",
        )
        self.service.ingest_event(event)

        result = self.service.retrieve(RetrievalQuery("team 客户 A xlsx"), include_trace=True)

        self.assertEqual(result.ranked_memories, [])
        self.assertEqual(result.trace["mode"], "memory_core_fallback")
        self.assertEqual(result.trace["candidate_count"], 0)

    def test_duplicate_team_retention_reinforces_review_schedule(self) -> None:
        event = NormalizedEvent(
            event_id="event-retention-dup-1",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：客户 A 要求导出文件使用 xlsx。",
        )
        duplicate = NormalizedEvent(
            event_id="event-retention-dup-2",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-28T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：客户 A 要求导出文件使用 xlsx。",
        )

        memory_id = self.service.ingest_event(event).memory_ids[0]
        duplicate_id = self.service.ingest_event(duplicate).memory_ids[0]

        self.assertEqual(duplicate_id, memory_id)
        self.assertEqual(self.team_retention_store.get_review_schedule(memory_id).review_count, 1)

    def test_update_missing_memory_returns_error(self) -> None:
        with self.assertRaises(ValueError):
            self.service.update_memory("expire", memory_id="missing-memory")

    def test_maintenance_includes_team_review_due_suggestions(self) -> None:
        event = NormalizedEvent(
            event_id="event-retention-maintenance",
            event_type="chat_message",
            source_type="feishu_chat",
            occurred_at="2026-04-27T00:00:00Z",
            context=EventContext(team_id="team-1", project_id="project-1"),
            content_text="请团队长期记住：API key 已更新，旧 key 不再使用。",
        )
        self.service.ingest_event(event)

        result = self.service.run_maintenance()

        self.assertIn("review_due", result)
        self.assertGreaterEqual(len(result["review_due"].suggestions), 1)
