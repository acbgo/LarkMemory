from __future__ import annotations

import pytest
from src.domains.cli_workflow.models import (
    CLIWorkflowCandidate,
    CLIWorkflowMemory,
    ParameterBinding,
    _param_tags_to_bindings,
)


class TestParameterBinding:
    def test_create(self):
        pb = ParameterBinding(param_name="env", param_value="prod", frequency=5)
        assert pb.param_name == "env"
        assert pb.param_value == "prod"
        assert pb.frequency == 5

    def test_default_frequency(self):
        pb = ParameterBinding(param_name="region", param_value="cn-shanghai")
        assert pb.frequency == 1


class TestCLIWorkflowMemory:
    def test_create_minimal(self):
        memory = CLIWorkflowMemory(
            user_id="u_1",
            command_template="lark project deploy --env {env}",
            command_name="lark project deploy",
        )
        assert memory.user_id == "u_1"
        assert memory.command_name == "lark project deploy"
        assert memory.execution_count == 1
        assert memory.status == "active"

    def test_to_memory_core(self):
        memory = CLIWorkflowMemory(
            workflow_id="mem-test-1",
            user_id="u_1",
            command_template="lark project deploy --env {env}",
            command_name="lark project deploy",
            command_category="deploy",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="prod", frequency=5),
            ],
            execution_count=5,
            last_executed_at="2026-05-03T00:00:00Z",
            success_count=5,
            source_type="shell",
        )
        core = memory.to_memory_core()
        assert core.memory_id == "mem-test-1"
        assert core.domain == "cli_workflow"
        assert core.memory_type == "cli_workflow"
        assert core.scope == "user"
        assert "user_id:u_1" in core.entities
        assert "project_id:backend" in core.entities
        assert "command_name:lark project deploy" in core.entities
        assert "category:deploy" in core.tags
        assert "param:env=prod" in core.tags
        assert core.importance > 0
        assert core.confidence == 1.0

    def test_to_memory_core_no_project(self):
        memory = CLIWorkflowMemory(
            workflow_id="mem-test-2",
            user_id="u_2",
            command_template="git push {remote} {branch}",
            command_name="git push",
        )
        core = memory.to_memory_core()
        assert "user_id:u_2" in core.entities
        assert "command_name:git push" in core.entities
        # no project_id entity when project_id is None
        project_entities = [e for e in core.entities if e.startswith("project_id:")]
        assert len(project_entities) == 0

    def test_from_memory_core_roundtrip(self):
        memory = CLIWorkflowMemory(
            workflow_id="mem-test-3",
            user_id="u_1",
            command_template="lark project deploy --env {env} --region {region}",
            command_name="lark project deploy",
            command_category="deploy",
            project_id="backend",
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="prod", frequency=10),
                ParameterBinding(param_name="region", param_value="cn-shanghai", frequency=10),
            ],
            execution_count=10,
            last_executed_at="2026-05-03T00:00:00Z",
            success_count=9,
            source_type="shell",
        )
        core = memory.to_memory_core()
        restored = CLIWorkflowMemory.from_memory_core(core)
        assert restored.workflow_id == memory.workflow_id
        assert restored.user_id == memory.user_id
        assert restored.command_name == memory.command_name
        assert restored.command_template == memory.command_template
        assert restored.command_category == memory.command_category
        assert restored.project_id == memory.project_id
        assert restored.execution_count == memory.execution_count
        assert restored.source_type == memory.source_type
        assert len(restored.parameter_bindings) == 2

    def test_success_rate(self):
        memory = CLIWorkflowMemory(execution_count=10, success_count=7)
        assert memory.success_rate == 0.7

    def test_success_rate_zero_count(self):
        memory = CLIWorkflowMemory(execution_count=0, success_count=0)
        assert memory.success_rate == 0.0

    def test_build_content_text(self):
        memory = CLIWorkflowMemory(
            command_template="lark project deploy --env {env}",
            command_name="lark project deploy",
            command_category="deploy",
            project_id="backend",
            execution_count=5,
            success_count=5,
            parameter_bindings=[
                ParameterBinding(param_name="env", param_value="prod", frequency=5),
            ],
        )
        text = memory.build_content_text()
        assert "lark project deploy --env {env}" in text
        assert "backend" in text
        assert "env prod" in text

    def test_build_summary_text(self):
        memory = CLIWorkflowMemory(
            command_template="git log --max-count {max-count} --oneline",
            command_name="git log",
            command_category="vcs",
            execution_count=3,
            parameter_bindings=[
                ParameterBinding(param_name="max-count", param_value="5", frequency=3),
            ],
        )
        summary = memory.build_summary_text()
        assert "git log --max-count 5 --oneline" in summary
        assert "git log" in summary
        assert "vcs" in summary
        assert "--max-count" in summary
        assert "3次" in summary

    def test_to_dict(self):
        memory = CLIWorkflowMemory(
            workflow_id="mem-dict-1",
            user_id="u_1",
            command_template="git push {remote}",
            command_name="git push",
            parameter_bindings=[
                ParameterBinding(param_name="remote", param_value="origin", frequency=3),
            ],
        )
        d = memory.to_dict()
        assert d["workflow_id"] == "mem-dict-1"
        assert d["user_id"] == "u_1"
        assert len(d["parameter_bindings"]) == 1
        assert d["parameter_bindings"][0]["param_name"] == "remote"

    def test_importance_increases_with_count(self):
        m1 = CLIWorkflowMemory(execution_count=1)
        m5 = CLIWorkflowMemory(execution_count=5)
        m50 = CLIWorkflowMemory(execution_count=50)
        i1 = m1._execution_importance()
        i5 = m5._execution_importance()
        i50 = m50._execution_importance()
        assert i1 < i5 < i50


class TestParamTagsToBindings:
    def test_single_param(self):
        bindings = _param_tags_to_bindings(["param:env=prod"])
        assert len(bindings) == 1
        assert bindings[0].param_name == "env"
        assert bindings[0].param_value == "prod"
        assert bindings[0].frequency == 1

    def test_duplicate_param_same_value(self):
        bindings = _param_tags_to_bindings(["param:env=prod", "param:env=prod"])
        assert len(bindings) == 1
        assert bindings[0].frequency == 2

    def test_duplicate_param_different_value(self):
        bindings = _param_tags_to_bindings(["param:env=prod", "param:env=staging"])
        assert len(bindings) == 2

    def test_invalid_param_tag(self):
        bindings = _param_tags_to_bindings(["param:=value", "param:name=", "param:="])
        assert len(bindings) == 0

    def test_non_param_tags(self):
        bindings = _param_tags_to_bindings(["cli_workflow", "category:deploy", "param:env=prod"])
        assert len(bindings) == 1


class TestCLIWorkflowCandidate:
    def test_admissible_with_params(self):
        candidate = CLIWorkflowCandidate(
            memory=CLIWorkflowMemory(
                command_template="lark deploy --env {env}",
                command_name="lark deploy",
                parameter_bindings=[ParameterBinding(param_name="env", param_value="prod")],
            ),
            evidence_text="lark deploy --env prod",
        )
        assert candidate.is_admissible() is True

    def test_not_admissible_no_template(self):
        candidate = CLIWorkflowCandidate(
            memory=CLIWorkflowMemory(
                command_template="",
                command_name="",
            ),
            evidence_text="",
        )
        assert candidate.is_admissible() is False

    def test_admissible_no_params_high_count(self):
        candidate = CLIWorkflowCandidate(
            memory=CLIWorkflowMemory(
                command_template="git pull",
                command_name="git pull",
                execution_count=5,
            ),
            evidence_text="git pull",
        )
        assert candidate.is_admissible() is True

    def test_not_admissible_no_params_low_count(self):
        candidate = CLIWorkflowCandidate(
            memory=CLIWorkflowMemory(
                command_template="git pull",
                command_name="git pull",
                execution_count=1,
            ),
            evidence_text="git pull",
        )
        assert candidate.is_admissible() is False
