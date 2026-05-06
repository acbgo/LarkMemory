from __future__ import annotations

import hashlib
import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from src.core import MemoryService
from src.domains.project_decision import ProjectDecisionDomainHandler
from src.sources.feishu.client.listener import _doc_changed_from_lark
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.sources.feishu.events.doc_models import FeishuDocChangedEvent
from src.sources.feishu.events.doc_normalizer import doc_section_to_event
from src.sources.feishu.events.doc_processor import DocProcessor
from src.storage import EventStore, MemoryCoreStore
from src.storage.source_state_store import SourceStateStore


class TestDocNormalizer(unittest.TestCase):

    def test_doc_section_to_event(self) -> None:
        event = doc_section_to_event(
            "## 架构设计\n\n后端使用 Python，前端使用 React。",
            "架构设计",
            "h-000-abc123def456",
            "doc_token_001",
            "技术方案文档",
            0,
        )

        self.assertEqual(event.event_type, "doc_section")
        self.assertEqual(event.source_type, "feishu_doc")
        self.assertIn("h-000-abc123def456", event.event_id)
        self.assertEqual(event.title, "架构设计")
        self.assertIn("Python", event.content_text)
        self.assertEqual(event.payload["doc_token"], "doc_token_001")
        self.assertEqual(event.payload["doc_title"], "技术方案文档")
        self.assertEqual(event.payload["section_index"], 0)
        self.assertIn("doc", event.tags)
        self.assertIn("section", event.tags)

    def test_doc_section_can_bind_team_scope(self) -> None:
        event = doc_section_to_event(
            "## 文档事件 Demo 决策\n\nRetrieve API 的默认 top_k 调整为 8。",
            "文档事件 Demo 决策",
            "h-001-abcdef123456",
            "doc_token_team",
            "LarkMemory 项目",
            1,
            team_id="oc_b9cef0cb9a14fe72a58793560cc4aa1c",
        )

        self.assertEqual(event.context.team_id, "oc_b9cef0cb9a14fe72a58793560cc4aa1c")
        self.assertEqual(event.context.scope, "team")
        self.assertIsNone(event.context.project_id)
        self.assertIsNone(event.context.workspace_id)

    def test_doc_section_falls_back_to_doc_title(self) -> None:
        event = doc_section_to_event(
            "无标题段落的正文内容。",
            None,
            "chunk-002-abcdef",
            "doc_token_002",
            "项目周报",
            2,
        )

        self.assertEqual(event.title, "项目周报")

    def test_doc_section_falls_back_to_generic_title(self) -> None:
        event = doc_section_to_event(
            "正文内容",
            None,
            "chunk-003-fallback",
            "doc_token_003",
            None,
            0,
        )

        self.assertEqual(event.title, "章节 1")


class TestDocProcessor(unittest.TestCase):
    def setUp(self) -> None:
        root = Path.cwd() / ".tmp-tests"
        root.mkdir(exist_ok=True)
        self.temp_dir = root / f"doc-proc-{uuid.uuid4().hex}"
        self.temp_dir.mkdir()
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

        self.event_store = EventStore(str(self.temp_dir / "events.db"))
        self.event_store.create_table()
        self.memory_store = MemoryCoreStore(str(self.temp_dir / "memory.db"))
        self.memory_store.create_table()
        self.service = MemoryService(
            event_store=self.event_store,
            memory_store=self.memory_store,
            domain_handlers=[ProjectDecisionDomainHandler(self.memory_store)],
        )
        self.state_store = SourceStateStore(str(self.temp_dir / "source_state.db"))
        self.state_store.create_table()
        self.dispatcher = FeishuEventDispatcher(self.service)

    def _make_content(self) -> str:
        return (
            "# 技术方案\n\n方案正文内容。\n\n"
            "## 架构选型\n\n后端选型讨论。\n\n"
            "## 部署方案\n\n部署相关说明。"
        )

    class _FakeDocClient:
        def __init__(self, content: str) -> None:
            self.content = content
            self.fetch_calls: list[str] = []

        def fetch_doc_content(self, doc_token: str) -> str:
            self.fetch_calls.append(doc_token)
            return self.content

    def test_processor_full_pipeline(self) -> None:
        content = self._make_content()
        doc_client = self._FakeDocClient(content)
        processor = DocProcessor(self.state_store, doc_client, self.dispatcher)

        processor._process("doc_full")

        self.assertEqual(doc_client.fetch_calls, ["doc_full"])

        state = self.state_store.get_state("feishu_doc", "doc_full")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state["status"], "complete")
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(state["last_hash"], expected_hash)
        self.assertEqual(state["metadata"]["section_count"], 3)

    def test_processor_skips_unchanged_doc(self) -> None:
        content = self._make_content()
        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.state_store.upsert_state(
            "feishu_doc", "doc_same", status="complete", last_hash=new_hash
        )

        doc_client = self._FakeDocClient(content)
        processor = DocProcessor(self.state_store, doc_client, self.dispatcher)
        processor._process("doc_same")

        # fetch 仍然会执行，但 hash 相同不应产生新事件
        self.assertEqual(doc_client.fetch_calls, ["doc_same"])
        events = self.event_store.list_events(limit=20)
        doc_events = [e for e in events if "doc_same" in e.get("event_id", "")]
        self.assertEqual(len(doc_events), 0)

    def test_processor_updates_hash_on_change(self) -> None:
        old_content = "# 旧标题\n\n旧内容"
        old_hash = hashlib.sha256(old_content.encode("utf-8")).hexdigest()
        self.state_store.upsert_state(
            "feishu_doc", "doc_changed", status="complete", last_hash=old_hash
        )

        new_content = "# 新标题\n\n新内容已更新"
        doc_client = self._FakeDocClient(new_content)
        processor = DocProcessor(self.state_store, doc_client, self.dispatcher)
        processor._process("doc_changed")

        state = self.state_store.get_state("feishu_doc", "doc_changed")
        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
        self.assertEqual(state["last_hash"], new_hash)

    def test_processor_dispatches_sections(self) -> None:
        content = "# 项目概述\n\n概述内容。\n\n## 需求分析\n\n需求内容。"
        doc_client = self._FakeDocClient(content)
        processor = DocProcessor(self.state_store, doc_client, self.dispatcher)
        processor._process("doc_dispatch")

        events = self.event_store.list_events(limit=20)
        event_ids = [e["event_id"] for e in events]
        self.assertTrue(any("doc:doc_dispatch:h-" in eid for eid in event_ids), f"events: {event_ids}")
        self.assertEqual(len(event_ids), 2)

    def test_processor_binds_sections_to_default_team_scope(self) -> None:
        content = "# 项目概述\n\n概述内容。\n\n## 需求分析\n\n需求内容。"
        doc_client = self._FakeDocClient(content)
        processor = DocProcessor(
            self.state_store,
            doc_client,
            self.dispatcher,
            team_id="oc_b9cef0cb9a14fe72a58793560cc4aa1c",
        )
        processor._process("doc_team_scope")

        events = self.event_store.list_events(limit=20)
        doc_events = [event for event in events if "doc_team_scope" in event.get("event_id", "")]
        self.assertEqual(len(doc_events), 2)
        for event in doc_events:
            self.assertEqual(event["team_id"], "oc_b9cef0cb9a14fe72a58793560cc4aa1c")
            self.assertEqual(event["scope"], "team")
            self.assertIsNone(event["project_id"])
            self.assertIsNone(event["workspace_id"])

    def test_processor_empty_content(self) -> None:
        doc_client = self._FakeDocClient("")
        processor = DocProcessor(self.state_store, doc_client, self.dispatcher)
        processor._process("doc_empty")

        self.assertEqual(doc_client.fetch_calls, ["doc_empty"])
        state = self.state_store.get_state("feishu_doc", "doc_empty")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["last_hash"], "")


class TestDocEventFromLark(unittest.TestCase):

    def test_extracts_basic_fields(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(
                file_token="doc_lark_001",
                file_type="docx",
                operator_id_list=[
                    SimpleNamespace(open_id="ou_editor"),
                ],
            ),
        )

        doc = _doc_changed_from_lark(data)
        self.assertIsNotNone(doc)
        assert doc is not None
        self.assertEqual(doc.file_token, "doc_lark_001")
        self.assertEqual(doc.file_type, "docx")
        self.assertEqual(doc.user_id, "ou_editor")

    def test_returns_none_when_no_event(self) -> None:
        self.assertIsNone(_doc_changed_from_lark(SimpleNamespace(event=None)))

    def test_returns_none_when_no_file_token(self) -> None:
        data = SimpleNamespace(
            event=SimpleNamespace(file_token=None)
        )
        self.assertIsNone(_doc_changed_from_lark(data))
