from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from src.domains.team_retention import TeamRetentionVersionManager
from src.storage import MemoryCoreStore, TeamRetentionMemory, TeamRetentionStore


def test_detects_and_applies_team_retention_supersede() -> None:
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    temp_dir = root / f"team-retention-version-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        db_path = str(temp_dir / "memory.db")
        memory_store = MemoryCoreStore(db_path)
        memory_store.create_table()
        team_store = TeamRetentionStore(db_path)
        team_store.create_table()
        old = TeamRetentionMemory(
            retention_id="mem-old",
            team_id="team-1",
            fact_type="customer_preference",
            fact_value="客户 A 要求导出 xlsx",
            version_group="team-1:customer-a-export",
        )
        new = TeamRetentionMemory(
            retention_id="mem-new",
            team_id="team-1",
            fact_type="customer_preference",
            fact_value="客户 A 现在接受 csv，但必须 UTF-8 编码",
            version_group="team-1:customer-a-export",
        )
        memory_store.insert_memory_core(old.to_memory_core())
        memory_store.insert_memory_core(new.to_memory_core())
        team_store.insert_memory(old)
        team_store.insert_memory(new)
        team_store.create_review_schedule(old)
        team_store.create_review_schedule(new)

        manager = TeamRetentionVersionManager(memory_store, team_store)
        decision = manager.detect_update(new)
        manager.apply_supersede("mem-old", "mem-new")

        assert decision.should_supersede
        assert decision.old_memory_id == "mem-old"
        assert memory_store.get_memory("mem-old")["status"] == "superseded"
        assert team_store.get_review_schedule("mem-old").active is False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
