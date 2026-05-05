from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from src.core.domain_handler import DomainRuntime
from src.domains.cli_workflow.handler import CLIWorkflowDomainHandler
from src.domains.cli_workflow.models import CLIWorkflowMemory
from src.schemas.event import EventContext, NormalizedEvent
from src.storage.event_store import EventStore
from src.storage.cli_workflow_store import CLIWorkflowStore
from src.storage.memory_core_store import MemoryCoreStore
from src.utils.ids import event_id
from src.utils.time import utc_now_iso


@pytest.fixture
def temp_dir():
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    d = root / f"cli-workflow-handler-{uuid.uuid4().hex}"
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def stores(temp_dir):
    db_path = str(temp_dir / "test_cli.db")
    event_store = EventStore(db_path)
    event_store.create_table()
    memory_store = MemoryCoreStore(db_path)
    memory_store.create_table()
    return event_store, memory_store


def make_shell_event(command: str, *, project_id: str = "backend", user_id: str = "u_1") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id(),
        event_type="command_finished",
        source_type="shell",
        occurred_at=utc_now_iso(),
        context=EventContext(user_id=user_id, project_id=project_id, scope="user"),
        content_text=command,
        payload={"exit_code": 0, "cwd": f"/home/user/projects/{project_id}", "duration_ms": 1200},
    )


def _add_memory(storage: MemoryCoreStore):
    def add(memory):
        storage.insert_memory_core(memory)
        return memory.memory_id
    return add


class TestHandlerIngest:
    def test_ingest_shell_event_creates_memory(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        event = make_shell_event("lark project deploy --env prod --region cn-shanghai")
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=_add_memory(memory_store),
        )
        result = handler.ingest_event(event, runtime)
        assert result.candidate_count == 1
        assert len(result.memory_ids) == 1

        core = memory_store.get_memory(result.memory_ids[0])
        assert core is not None
        assert core["domain"] == "cli_workflow"
        assert core["scope"] == "user"

    def test_known_toolchain_command_without_params_is_stored(self, stores):
        """Known toolchain commands without flags are useful command patterns."""
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        event = make_shell_event("git pull", project_id="backend")
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=_add_memory(memory_store),
        )
        result = handler.ingest_event(event, runtime)
        assert len(result.memory_ids) == 1

    def test_ingest_trivial_command_returns_no_candidates(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        event = make_shell_event("ls -la")
        runtime = DomainRuntime(
            memory_store=memory_store,
            add_memory=_add_memory(memory_store),
        )
        result = handler.ingest_event(event, runtime)
        assert result.candidate_count == 0
        assert len(result.memory_ids) == 0

    def test_reinforce_same_command(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        event1 = make_shell_event("lark project deploy --env prod")
        runtime1 = DomainRuntime(memory_store=memory_store, add_memory=add)
        result1 = handler.ingest_event(event1, runtime1)
        assert result1.candidate_count == 1

        event2 = make_shell_event("lark project deploy --env prod")
        runtime2 = DomainRuntime(memory_store=memory_store, add_memory=add)
        result2 = handler.ingest_event(event2, runtime2)
        assert result2.candidate_count == 1

        assert result1.memory_ids[0] == result2.memory_ids[0]

        core = memory_store.get_memory(result1.memory_ids[0])
        restored = CLIWorkflowMemory.from_memory_core(core)
        assert restored.execution_count == 2

    def test_same_command_different_project_creates_new_memory(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        event1 = make_shell_event("lark project deploy --env prod", project_id="backend")
        runtime1 = DomainRuntime(memory_store=memory_store, add_memory=add)
        result1 = handler.ingest_event(event1, runtime1)

        event2 = make_shell_event("lark project deploy --env prod", project_id="frontend")
        runtime2 = DomainRuntime(memory_store=memory_store, add_memory=add)
        result2 = handler.ingest_event(event2, runtime2)

        assert result1.memory_ids[0] != result2.memory_ids[0]

    def test_openclaw_overrides_shell(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        shell_event = make_shell_event("lark project deploy --env prod")
        runtime_shell = DomainRuntime(memory_store=memory_store, add_memory=add)
        result_shell = handler.ingest_event(shell_event, runtime_shell)

        oc_event = NormalizedEvent(
            event_id=event_id(),
            event_type="memory_feedback",
            source_type="openclaw",
            occurred_at=utc_now_iso(),
            context=EventContext(user_id="u_1", project_id="backend", scope="user"),
            content_text='记住：部署用 "lark project deploy --env staging"',
            payload={"intent": "teach_command"},
        )
        runtime_oc = DomainRuntime(memory_store=memory_store, add_memory=add)
        result_oc = handler.ingest_event(oc_event, runtime_oc)

        old_core = memory_store.get_memory(result_shell.memory_ids[0])
        assert old_core["status"] == "superseded"
        assert old_core["superseded_by"] == result_oc.memory_ids[0]

    def test_ingest_syncs_structured_cli_tables(self, temp_dir):
        db_path = str(temp_dir / "test_structured_cli.db")
        memory_store = MemoryCoreStore(db_path)
        memory_store.create_table()
        cli_store = CLIWorkflowStore(db_path)
        cli_store.create_table()
        handler = CLIWorkflowDomainHandler(memory_store, cli_store=cli_store)
        add = _add_memory(memory_store)

        shell_event = make_shell_event("lark project deploy --env prod", project_id="backend")
        shell_result = handler.ingest_event(
            shell_event,
            DomainRuntime(memory_store=memory_store, add_memory=add),
        )
        patterns = cli_store.list_patterns(user_id="u_1", project_id="backend")
        assert shell_result.memory_ids[0] == patterns[0]["memory_id"]
        assert patterns[0]["memory_origin"] == "observed"

        oc_event = NormalizedEvent(
            event_id=event_id(),
            event_type="memory_feedback",
            source_type="openclaw",
            occurred_at=utc_now_iso(),
            context=EventContext(user_id="u_1", project_id="backend", scope="user"),
            content_text="记住部署 demo-a 的时候参数 env 设置为 staging",
            payload={"intent": "teach_command"},
        )
        policy_result = handler.ingest_event(
            oc_event,
            DomainRuntime(memory_store=memory_store, add_memory=add),
        )
        policies = cli_store.list_parameter_policies(user_id="u_1", project_id="backend")

        assert policy_result.candidate_count == 1
        assert policies[0]["param_name"] == "env"
        assert policies[0]["param_value"] == "staging"


class TestHandlerRetrieve:
    def test_retrieve_returns_ranked_memories(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        event = make_shell_event("lark project deploy --env prod --region cn-shanghai")
        runtime = DomainRuntime(memory_store=memory_store, add_memory=add)
        handler.ingest_event(event, runtime)

        from src.retrieval import RetrievalQuery
        query = RetrievalQuery(
            query_text="deploy",
            user_id="u_1",
            project_id="backend",
        )
        results = handler.retrieve(query, top_k=5)
        assert len(results) >= 1
        assert results[0].item.domain.value == "cli_workflow"

    def test_retrieve_empty_when_no_match(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        event = make_shell_event("lark project deploy --env prod")
        runtime = DomainRuntime(memory_store=memory_store, add_memory=add)
        handler.ingest_event(event, runtime)

        from src.retrieval import RetrievalQuery
        query = RetrievalQuery(
            query_text="build",
            user_id="u_2",
        )
        results = handler.retrieve(query, top_k=5)
        assert len(results) == 0

    def test_reinforce_keeps_old_param_values(self, stores):
        """When param value changes, old value frequency should not be decayed."""
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        e1 = make_shell_event("lark project deploy --env prod")
        r1 = handler.ingest_event(e1, DomainRuntime(memory_store=memory_store, add_memory=add))

        e2 = make_shell_event("lark project deploy --env staging")
        r2 = handler.ingest_event(e2, DomainRuntime(memory_store=memory_store, add_memory=add))

        # Same memory should be reinforced (same user+project+command)
        assert r1.memory_ids[0] == r2.memory_ids[0]

        core = memory_store.get_memory(r1.memory_ids[0])
        restored = CLIWorkflowMemory.from_memory_core(core)
        bindings = {(pb.param_name, pb.param_value): pb.frequency for pb in restored.parameter_bindings}
        # Both prod and staging should be present
        assert ("env", "prod") in bindings
        assert ("env", "staging") in bindings
        # Old value frequency should not have been decremented
        assert bindings[("env", "prod")] == 1

    def test_retrieve_filters_by_project(self, stores):
        _, memory_store = stores
        handler = CLIWorkflowDomainHandler(memory_store)
        add = _add_memory(memory_store)

        event1 = make_shell_event("lark project deploy --env prod", project_id="backend")
        runtime1 = DomainRuntime(memory_store=memory_store, add_memory=add)
        handler.ingest_event(event1, runtime1)

        from src.retrieval import RetrievalQuery
        query = RetrievalQuery(
            query_text="deploy",
            user_id="u_1",
            project_id="frontend",
        )
        results = handler.retrieve(query, top_k=5)
        assert len(results) == 0
