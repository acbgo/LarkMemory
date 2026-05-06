from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from src.domains.cli_workflow.models import CLIWorkflowMemory, ParameterBinding
from src.storage.cli_workflow_store import CLIWorkflowStore


@pytest.fixture
def cli_store() -> CLIWorkflowStore:
    root = Path.cwd() / ".tmp-tests" / f"cli-store-{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    store = CLIWorkflowStore(str(root / "cli.db"))
    store.create_table()
    yield store
    shutil.rmtree(root, ignore_errors=True)


def test_upsert_pattern_accumulates_frequency_by_table(cli_store: CLIWorkflowStore) -> None:
    memory = CLIWorkflowMemory(
        workflow_id="mem-1",
        user_id="u_1",
        project_id="Demo",
        command_template="python deploy.py --stage {stage}",
        command_name="python deploy.py",
        parameter_bindings=[ParameterBinding("stage", "staging")],
        execution_count=1,
        success_count=1,
        source_type="shell",
    )

    cli_store.upsert_pattern(memory, cwd="/workspace/demo")
    cli_store.upsert_pattern(memory, cwd="/workspace/demo")

    rows = cli_store.list_patterns(user_id="u_1", project_id="Demo")
    assert len(rows) == 1
    assert rows[0]["execution_count"] == 2
    assert cli_store.sub_command_frequency(user_id="u_1", project_id="Demo")["python deploy.py"] == 2


def test_parameter_policy_supersedes_old_value(cli_store: CLIWorkflowStore) -> None:
    old_id = cli_store.upsert_parameter_policy(
        scenario_text="部署 demo-a 时参数 stage 设置为 staging",
        param_name="stage",
        param_value="staging",
        user_id="u_1",
        project_id="Demo",
    )
    new_id = cli_store.upsert_parameter_policy(
        scenario_text="部署 demo-a 时参数 stage 设置为 prod",
        param_name="stage",
        param_value="prod",
        user_id="u_1",
        project_id="Demo",
    )

    active = cli_store.list_parameter_policies(user_id="u_1", project_id="Demo")
    assert [item["policy_id"] for item in active] == [new_id]
    old = cli_store.fetch_one("SELECT * FROM cli_parameter_policy WHERE policy_id = ?", (old_id,))
    assert old is not None
    assert old["status"] == "superseded"
    assert old["superseded_by"] == new_id


def test_parameter_policy_keeps_same_param_in_different_scenarios(cli_store: CLIWorkflowStore) -> None:
    deploy_id = cli_store.upsert_parameter_policy(
        scenario_text="部署 demo-a 时参数 env 设置为 staging",
        scenario_signature="部署 demo-a",
        target_sub_command="python deploy.py",
        param_name="env",
        param_value="staging",
        user_id="u_1",
        project_id="Demo",
    )
    rollback_id = cli_store.upsert_parameter_policy(
        scenario_text="回滚 demo-a 时参数 env 设置为 prod",
        scenario_signature="回滚 demo-a",
        target_sub_command="python rollback.py",
        param_name="env",
        param_value="prod",
        user_id="u_1",
        project_id="Demo",
    )

    active = cli_store.list_parameter_policies(user_id="u_1", project_id="Demo")
    assert {item["policy_id"] for item in active} == {deploy_id, rollback_id}


def test_extract_explicit_parameter_policy_from_text(cli_store: CLIWorkflowStore) -> None:
    ids = cli_store.upsert_parameter_policy_from_text(
        "记住部署 demo-a 的时候参数 stage 设置为 staging",
        user_id="u_1",
        project_id="Demo",
    )

    assert len(ids) == 1
    active = cli_store.list_parameter_policies(user_id="u_1", project_id="Demo")
    assert active[0]["param_name"] == "stage"
    assert active[0]["param_value"] == "staging"
