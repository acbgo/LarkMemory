from __future__ import annotations

import asyncio

import pytest
from src.llm.base import LLMJSONDecodeError
from src.core.domain_classifier import (
    ALL_DOMAINS,
    DomainClassifier,
)


class FakeLLM:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls: list[dict[str, object]] = []

    async def atext(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> str:
        self.calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        return self.label


class FakeJsonLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.json_calls: list[dict[str, object]] = []
        self.text_calls: list[dict[str, object]] = []

    async def ajson(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> dict[str, object]:
        self.json_calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        return self.payload

    async def atext(self, system_prompt: str | None, user_prompt: str, **kwargs: object) -> str:
        self.text_calls.append({"system_prompt": system_prompt or "", "user_prompt": user_prompt, "kwargs": kwargs})
        return "team_retention"


class EmptyTextLLM:
    async def atext(self, *_args: object, **_kwargs: object) -> str:
        return ""


class JSONDecodeFailingLLM:
    async def ajson(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise LLMJSONDecodeError("bad json", content='{"primary":"project_decision"')

    async def atext(self, *_args: object, **_kwargs: object) -> str:
        return "project_decision"


class FailingLLM:
    async def atext(self, *_args: object, **_kwargs: object) -> str:
        raise RuntimeError("LLM unavailable")


# ---------------------------------------------------------------------------
# keyword classification
# ---------------------------------------------------------------------------

class TestKeywordClassification:
    def test_cli_workflow_hit(self):
        c = DomainClassifier()
        result = c.classify_sync("部署后台服务 --env prod")
        assert result.primary == ["cli_workflow"]
        assert result.method == "keyword_rule"

    def test_project_decision_hit(self):
        c = DomainClassifier()
        result = c.classify_sync("团队决定采用方案B")
        assert result.primary == ["project_decision"]

    @pytest.mark.parametrize(
        "text",
        [
            "支付模块出故障了怎么办",
            "成本预算费用采购",
            "API 网关限流策略",
            "张三负责什么 李四负责什么",
            "支付回调超时如何处理",
            "公开 API 现在的默认限流阈值是多少",
        ],
    )
    def test_project_decision_benchmark_queries_route_to_project_decision(self, text: str):
        c = DomainClassifier()
        result = c.classify_sync(text)
        assert result.primary[0] == "project_decision"

    def test_release_decision_signal_uses_llm_before_keyword_fallback(self):
        c = DomainClassifier(llm_client=FakeLLM("cli_workflow"))
        result = c.classify_sync("上线脚本已通过演练。结论：v2.3 准予上线，按 5%-20%-100% 灰度发布。")
        assert result.primary == ["cli_workflow"]
        assert result.method == "llm"

    def test_release_decision_signal_falls_back_to_project_decision_when_llm_unavailable(self):
        c = DomainClassifier(llm_client=FailingLLM())
        result = c.classify_sync("上线脚本已通过演练。结论：v2.3 准予上线，按 5%-20%-100% 灰度发布。")
        assert result.primary[0] == "project_decision"
        assert result.method == "keyword_rule"

    def test_personal_preference_hit(self):
        c = DomainClassifier()
        result = c.classify_sync("用户偏好默认中文")
        assert result.primary == ["personal_preference"]

    def test_team_retention_hit(self):
        c = DomainClassifier()
        result = c.classify_sync("请团队长期记住客户要求")
        assert result.primary == ["team_retention"]

    def test_dual_primary_both_domains_match(self):
        c = DomainClassifier()
        result = c.classify_sync("团队长期记住部署命令 --env staging")
        primary_set = set(result.primary)
        assert "cli_workflow" in primary_set
        assert "team_retention" in primary_set
        assert len(result.primary) == 2

    def test_dual_primary_gets_secondary_affinity(self):
        c = DomainClassifier()
        result = c.classify_sync("团队长期记住部署命令 --env staging")
        # Both cli_workflow and team_retention should contribute secondary domains
        # cli_workflow → team_retention (already in primary, skipped)
        # team_retention → project_decision
        assert "project_decision" in result.secondary

    def test_single_primary_gets_secondary_affinity(self):
        c = DomainClassifier()
        result = c.classify_sync("部署命令")
        assert result.primary == ["cli_workflow"]
        assert "team_retention" in result.secondary

    def test_zero_match_fallback(self):
        c = DomainClassifier()
        result = c.classify_sync("hello world nothing")
        assert result.primary == ["team_retention"]
        assert "project_decision" in result.secondary
        assert result.method == "keyword_rule"
        assert result.confidence == 0.3

    def test_keywords_in_result(self):
        c = DomainClassifier()
        result = c.classify_sync("部署生产环境")
        assert "部署" in result.keywords


# ---------------------------------------------------------------------------
# hard rules
# ---------------------------------------------------------------------------

class TestHardRules:
    def test_command_finished_routes_to_cli(self):
        c = DomainClassifier()
        result = c.classify_sync("anything", event_type="command_finished")
        assert result.primary == ["cli_workflow"]
        assert result.method == "event_type_rule"
        assert result.confidence == 0.9

    def test_command_failed_routes_to_cli(self):
        c = DomainClassifier()
        result = c.classify_sync("npm install failed", event_type="command_failed")
        assert result.primary == ["cli_workflow"]
        assert result.method == "event_type_rule"

    def test_memory_feedback_no_hard_rule(self):
        c = DomainClassifier()
        result = c.classify_sync("hello", event_type="memory_feedback")
        # memory_feedback has no hard rule → falls through to keywords
        assert result.method == "keyword_rule"


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

class TestLLMClassification:
    def test_llm_classify_returns_domain(self):
        llm = FakeLLM("cli_workflow")
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("deploy staging")
        assert result.primary == ["cli_workflow"]
        assert result.method == "llm"
        assert result.confidence == 0.8
        assert len(llm.calls) == 1

    def test_llm_classify_with_extra_text(self):
        llm = FakeLLM("  project_decision  ")
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("为什么选方案B")
        assert result.primary == ["project_decision"]
        assert result.method == "llm"

    def test_llm_classify_gets_keywords(self):
        llm = FakeLLM("cli_workflow")
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("部署命令 --env prod")
        assert len(result.keywords) >= 1

    def test_llm_classify_gets_secondary_affinity(self):
        llm = FakeLLM("cli_workflow")
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("deploy command")
        assert "team_retention" in result.secondary

    def test_llm_json_contract_is_preferred_over_text(self):
        llm = FakeJsonLLM({"primary": "project_decision", "confidence": 0.91, "reason": "rate limit decision"})
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("公开 API 现在的默认限流阈值是多少")
        assert result.primary == ["project_decision"]
        assert result.confidence == 0.91
        assert result.method == "llm_json"
        assert result.reason == "rate limit decision"
        assert len(llm.json_calls) == 1
        assert llm.text_calls == []
        kwargs = llm.json_calls[0]["kwargs"]
        assert kwargs["max_tokens"] >= 160
        assert isinstance(kwargs["schema"], dict)

    def test_llm_json_invalid_domain_falls_back_to_keywords(self):
        llm = FakeJsonLLM({"primary": "unknown", "confidence": 0.91, "reason": "bad"})
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("公开 API 现在的默认限流阈值是多少")
        assert result.primary[0] == "project_decision"
        assert result.method == "keyword_rule"

    def test_llm_empty_text_output_falls_back_without_traceback(self, caplog: pytest.LogCaptureFixture):
        c = DomainClassifier(llm_client=EmptyTextLLM())
        with caplog.at_level("INFO", logger="src.core.domain_classifier"):
            result = c.classify_sync("支付模块出故障了怎么办")
        assert result.primary[0] == "project_decision"
        assert result.method == "keyword_rule"
        logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "action=classify_llm_empty_output" in logs
        assert "Traceback" not in logs

    def test_llm_json_decode_error_falls_back_without_domain_traceback(self, caplog: pytest.LogCaptureFixture):
        c = DomainClassifier(llm_client=JSONDecodeFailingLLM())
        with caplog.at_level("INFO", logger="src.core.domain_classifier"):
            result = c.classify_sync("SQLite 数据库选型理由")
        assert result.primary == ["project_decision"]
        assert result.method == "llm"
        logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "action=classify_llm_json_decode_failed" in logs
        assert "Traceback" not in logs

    def test_llm_prompt_describes_project_decision_boundaries(self):
        llm = FakeLLM("project_decision")
        c = DomainClassifier(llm_client=llm)
        result = c.classify_sync("公开 API 现在的默认限流阈值是多少")
        prompt = str(llm.calls[0]["system_prompt"])
        assert result.primary == ["project_decision"]
        assert "default rate limits" in prompt
        assert "not personal_preference" in prompt
        assert "project_decision over cli_workflow" in prompt

    def test_llm_failure_falls_back_to_keywords(self):
        c = DomainClassifier(llm_client=FailingLLM())
        result = c.classify_sync("部署后端服务")
        assert result.primary == ["cli_workflow"]
        assert result.method == "keyword_rule"

    def test_llm_failure_falls_back_on_zero_match(self):
        c = DomainClassifier(llm_client=FailingLLM())
        result = c.classify_sync("xyz")
        assert result.primary == ["team_retention"]
        assert result.method == "keyword_rule"


# ---------------------------------------------------------------------------
# async path
# ---------------------------------------------------------------------------

class TestAsyncClassification:
    def test_async_keyword_classify(self):
        c = DomainClassifier()
        result = asyncio.run(c.classify("部署命令"))
        assert result.primary == ["cli_workflow"]

    def test_async_llm_classify(self):
        llm = FakeLLM("project_decision")
        c = DomainClassifier(llm_client=llm)
        result = asyncio.run(c.classify("为什么选方案B"))
        assert result.primary == ["project_decision"]
        assert result.method == "llm"

    def test_async_hard_rule(self):
        c = DomainClassifier()
        result = asyncio.run(c.classify("anything", event_type="command_finished"))
        assert result.primary == ["cli_workflow"]
        assert result.method == "event_type_rule"

    def test_async_llm_failure_falls_back(self):
        c = DomainClassifier(llm_client=FailingLLM())
        result = asyncio.run(c.classify("部署"))
        assert result.primary == ["cli_workflow"]
        assert result.method == "keyword_rule"


# ---------------------------------------------------------------------------
# parse_label
# ---------------------------------------------------------------------------

class TestParseLabel:
    def test_valid_labels(self):
        for domain in ALL_DOMAINS:
            assert DomainClassifier._parse_label(domain) == domain

    def test_label_with_whitespace(self):
        assert DomainClassifier._parse_label("  cli_workflow  ") == "cli_workflow"

    def test_label_with_extra_text(self):
        assert DomainClassifier._parse_label("primary: project_decision") == "project_decision"

    def test_invalid_label_raises(self):
        with pytest.raises(ValueError, match="invalid domain label"):
            DomainClassifier._parse_label("garbage")

    def test_empty_label_raises(self):
        with pytest.raises(ValueError, match="invalid domain label"):
            DomainClassifier._parse_label("")


# ---------------------------------------------------------------------------
# ALL_DOMAINS completeness
# ---------------------------------------------------------------------------

class TestAllDomains:
    def test_four_domains_registered(self):
        assert set(ALL_DOMAINS) == {
            "cli_workflow",
            "project_decision",
            "personal_preference",
            "team_retention",
        }
