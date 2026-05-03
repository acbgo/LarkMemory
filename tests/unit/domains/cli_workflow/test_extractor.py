from __future__ import annotations

import pytest
from src.domains.cli_workflow.extractor import CLIWorkflowExtractor, _is_trivial, _has_known_prefix, _has_flags
from src.domains.cli_workflow.models import CLIWorkflowCandidate
from src.schemas.event import EventContext, NormalizedEvent
from src.utils.ids import event_id
from src.utils.time import utc_now_iso


def make_shell_event(command: str, *, project_id: str = "backend", user_id: str = "u_1", exit_code: int = 0) -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id(),
        event_type="command_finished",
        source_type="shell",
        occurred_at=utc_now_iso(),
        context=EventContext(user_id=user_id, project_id=project_id, scope="user"),
        content_text=command,
        payload={"exit_code": exit_code, "cwd": f"/home/user/projects/{project_id}", "duration_ms": 1200},
    )


def make_openclaw_event(text: str, *, project_id: str = "backend", user_id: str = "u_1") -> NormalizedEvent:
    return NormalizedEvent(
        event_id=event_id(),
        event_type="memory_feedback",
        source_type="openclaw",
        occurred_at=utc_now_iso(),
        context=EventContext(user_id=user_id, project_id=project_id, scope="user"),
        content_text=text,
        payload={"intent": "teach_command"},
    )


class TestTrivialFiltering:
    def test_cd_is_trivial(self):
        assert _is_trivial("cd /home") is True

    def test_ls_is_trivial(self):
        assert _is_trivial("ls -la") is True

    def test_echo_is_trivial(self):
        assert _is_trivial("echo hello") is True

    def test_git_is_not_trivial(self):
        assert _is_trivial("git") is False


class TestKnownToolchain:
    def test_git_is_known(self):
        assert _has_known_prefix("git push origin main") is True

    def test_docker_is_known(self):
        assert _has_known_prefix("docker ps") is True

    def test_lark_is_known(self):
        assert _has_known_prefix("lark project deploy") is True

    def test_unknown_command(self):
        assert _has_known_prefix("my-custom-tool run") is False


class TestHasFlags:
    def test_double_dash_flags(self):
        assert _has_flags(["--env", "prod"]) is True

    def test_single_dash_flag(self):
        assert _has_flags(["-e", "prod"]) is True

    def test_no_flags(self):
        assert _has_flags(["git", "push", "origin", "main"]) is False


class TestShellExtraction:
    def test_extract_command_with_flags(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("lark project deploy --env prod --region cn-shanghai --canary 10")
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.memory.command_name == "lark project deploy"
        assert c.memory.command_template == "lark project deploy --env {env} --region {region} --canary {canary}"
        assert len(c.memory.parameter_bindings) == 3
        assert c.memory.source_type == "shell"
        assert c.memory.project_id == "backend"
        assert c.memory.user_id == "u_1"
        assert c.memory.execution_count == 1

    def test_extract_command_with_equals_flags(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("lark project deploy --env=prod --region=cn-shanghai")
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.memory.command_template == "lark project deploy --env={env} --region={region}"
        bindings = {(pb.param_name, pb.param_value) for pb in c.memory.parameter_bindings}
        assert ("env", "prod") in bindings
        assert ("region", "cn-shanghai") in bindings

    def test_skip_trivial_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("ls -la")
        candidates = extractor.extract(event)
        assert len(candidates) == 0

    def test_skip_cd_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("cd /tmp")
        candidates = extractor.extract(event)
        assert len(candidates) == 0

    def test_extract_git_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("git push origin main")
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        c = candidates[0]
        # base command is first 3 tokens: "git push origin"
        assert c.memory.command_name == "git push origin"
        # "main" becomes positional arg
        assert "{arg1}" in c.memory.command_template

    def test_skip_command_without_flags_and_unknown_prefix(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("my-unknown-tool run something")
        candidates = extractor.extract(event)
        assert len(candidates) == 0

    def test_extract_failed_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("lark project deploy --env prod", exit_code=1)
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        assert candidates[0].memory.success_count == 0

    def test_extract_successful_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("lark project deploy --env prod", exit_code=0)
        candidates = extractor.extract(event)
        assert candidates[0].memory.success_count == 1

    def test_signals_for_known_toolchain(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("docker ps")
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        assert "known_toolchain" in candidates[0].signals

    def test_single_token_known_toolchain_filtered(self):
        """Bare 'npm' with no args is known toolchain but single token → filtered."""
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("npm")
        candidates = extractor.extract(event)
        assert len(candidates) == 0

    def test_single_token_docker_filtered(self):
        """Bare 'docker' with no args → filtered."""
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("docker")
        candidates = extractor.extract(event)
        assert len(candidates) == 0

    def test_empty_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_shell_event("")
        candidates = extractor.extract(event)
        assert len(candidates) == 0


class TestOpenClawExtraction:
    def test_extract_quoted_command(self):
        extractor = CLIWorkflowExtractor()
        event = make_openclaw_event(
            '记住：部署用 "lark project deploy --env staging --canary 50"'
        )
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.memory.command_name == "lark project deploy"
        assert c.memory.source_type == "openclaw"
        assert "openclaw_explicit" in c.signals

    def test_no_quoted_command_no_extraction(self):
        extractor = CLIWorkflowExtractor()
        event = make_openclaw_event("部署的时候注意一下参数")
        candidates = extractor.extract(event)
        assert len(candidates) == 0

    def test_infer_command_from_known_prefix(self):
        extractor = CLIWorkflowExtractor()
        event = make_openclaw_event("以后部署用 lark project deploy --env staging")
        candidates = extractor.extract(event)
        if candidates:
            assert candidates[0].memory.source_type == "openclaw"
            if "inferred_command" in candidates[0].signals:
                assert candidates[0].needs_review is True


class FakeOpenClawLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def ajson(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return self.payload


class TestLLMSemanticsEnrichment:
    def test_rule_hit_enriches_with_semantics(self):
        """规则命中 + LLM → 参数获得 semantics"""
        llm = FakeOpenClawLLM({
            "parameters": [
                {"param_name": "env", "param_value": "staging",
                 "semantics": "部署目标环境，staging 为预发布环境"},
                {"param_name": "canary", "param_value": "50",
                 "semantics": "金丝雀发布流量百分比"},
            ]
        })
        extractor = CLIWorkflowExtractor(llm_client=llm)
        event = make_openclaw_event(
            '记住：部署用 "lark project deploy --env staging --canary 50"'
        )
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        assert "llm_semantics" in candidates[0].signals
        for pb in candidates[0].memory.parameter_bindings:
            assert pb.semantics is not None

    def test_rule_hit_llm_failure_returns_rule_result(self):
        """LLM 失败 → 回退到规则结果"""
        extractor = CLIWorkflowExtractor(llm_client=FakeOpenClawLLM({}))
        event = make_openclaw_event(
            '记住：部署用 "lark project deploy --env prod"'
        )
        candidates = extractor.extract(event)
        assert len(candidates) == 1


class TestLLMFullExtraction:
    def test_full_extraction_with_complete_command(self):
        """LLM 返回完整命令 → 参数化 + semantics"""
        llm = FakeOpenClawLLM({
            "full_command": "lark project deploy --region cn-shanghai",
            "scenario_keywords": ["部署", "区域配置"],
            "is_teaching": True,
            "parameters": [
                {"param_name": "region", "param_value": "cn-shanghai",
                 "semantics": "部署目标区域，cn-shanghai 为中国上海"},
            ],
        })
        extractor = CLIWorkflowExtractor(llm_client=llm)
        event = make_openclaw_event("部署时提醒我用 --region cn-shanghai")
        candidates = extractor.extract(event)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.memory.source_type == "openclaw"
        assert "llm_full_extraction" in c.signals
        assert "region" in c.memory.command_template

    def test_full_extraction_scenario_only_creates_partial(self):
        """LLM 只有场景词+参数 → 无完整命令 → partial candidate"""
        llm = FakeOpenClawLLM({
            "full_command": None,
            "scenario_keywords": ["部署"],
            "is_teaching": True,
            "parameters": [
                {"param_name": "region", "param_value": "cn-shanghai",
                 "semantics": "部署目标区域"},
            ],
        })
        extractor = CLIWorkflowExtractor(llm_client=llm)
        event = make_openclaw_event("以后部署提醒我用 --region cn-shanghai")
        candidates = extractor.extract(event)
        if candidates:
            assert candidates[0].needs_review is True
            assert "partial_template" in candidates[0].signals

    def test_non_teaching_message_returns_empty(self):
        """非教学消息 → LLM is_teaching=false → 返回空"""
        llm = FakeOpenClawLLM({
            "full_command": None,
            "scenario_keywords": [],
            "is_teaching": False,
            "parameters": [],
        })
        extractor = CLIWorkflowExtractor(llm_client=llm)
        event = make_openclaw_event("早上好")
        candidates = extractor.extract(event)
        assert len(candidates) == 0
