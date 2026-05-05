from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.domains.team_retention.models import TeamRetentionMemory
from src.storage import TeamRetentionStore


def _store() -> TeamRetentionStore:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"team-retention-store-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    store = TeamRetentionStore(str(temp_dir / "memory.db"))
    store.create_table()
    store._test_temp_dir = temp_dir  # type: ignore[attr-defined]
    return store


def _cleanup(store: TeamRetentionStore) -> None:
    shutil.rmtree(store._test_temp_dir, ignore_errors=True)  # type: ignore[attr-defined]


def test_insert_and_get_team_retention_memory() -> None:
    store = _store()
    try:
        memory = TeamRetentionMemory(
            retention_id="mem-team-1",
            team_id="team-1",
            project_id="project-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx",
            risk_level="medium",
            owner="pm",
            version_group="team-1:customer:a",
        )

        store.insert_memory(memory)
        fetched = store.get_memory("mem-team-1")

        assert fetched is not None
        assert fetched.fact_value == "客户 A 要求导出 xlsx"
        assert fetched.version_group == "team-1:customer:a"
    finally:
        _cleanup(store)


def test_review_schedule_due_review_and_mark_reviewed() -> None:
    store = _store()
    try:
        memory = TeamRetentionMemory(
            retention_id="mem-team-1",
            team_id="team-1",
            fact_value="API key 已更新",
            risk_level="high",
            created_at="2026-04-27T00:00:00Z",
        )
        store.insert_memory(memory)
        store.create_review_schedule(memory)

        due = store.list_due_reviews(now="2026-04-28T00:00:00Z", team_id="team-1")
        next_review_at = store.mark_reviewed("mem-team-1", reviewed_at="2026-04-28T00:00:00Z")

        assert len(due) == 1
        assert due[0].memory_id == "mem-team-1"
        assert next_review_at == "2026-04-29T00:00:00Z"  # ebbinghaus: stability=1.0, risk_mult=0.5, min_interval=1 day
        assert store.get_review_schedule("mem-team-1").review_count == 1
    finally:
        _cleanup(store)


def test_due_reviews_support_warning_window_and_snooze_missing_schedule_fails() -> None:
    store = _store()
    try:
        memory = TeamRetentionMemory(
            retention_id="mem-team-1",
            team_id="team-1",
            fact_value="客户 A 要求导出 xlsx",
            risk_level="medium",
            created_at="2026-04-27T00:00:00Z",
        )
        store.insert_memory(memory)
        store.create_review_schedule(memory)

        not_due = store.list_due_reviews(now="2026-04-27T12:00:00Z", team_id="team-1")
        warning = store.list_due_reviews(
            now="2026-04-27T12:00:00Z",
            warning_window_hours=12,
            team_id="team-1",
        )

        assert not_due == []
        assert len(warning) == 1
        try:
            store.snooze_review("missing")
        except ValueError as exc:
            assert "review schedule not found" in str(exc)
        else:
            raise AssertionError("missing schedule should fail")
    finally:
        _cleanup(store)
