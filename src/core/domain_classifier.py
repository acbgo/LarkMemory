from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

DomainLabel = Literal[
    "cli_workflow",
    "project_decision",
    "personal_preference",
    "team_retention",
]

ALL_DOMAINS: list[DomainLabel] = [
    "cli_workflow",
    "project_decision",
    "personal_preference",
    "team_retention",
]

_SECONDARY_AFFINITY: dict[DomainLabel, list[DomainLabel]] = {
    "cli_workflow": ["team_retention"],
    "project_decision": ["team_retention"],
    "personal_preference": [],
    "team_retention": ["project_decision"],
}

_KEYWORD_RULES: list[tuple[list[str], DomainLabel]] = [
    (
        [
            "部署", "deploy", "构建", "build", "运行", "run", "命令",
            "command", "shell", "终端", "terminal", "排障", "debug",
            "脚本", "script", "pipeline", "ci", "cd", "docker",
            "kubectl", "npm", "pip", "git", "pytest", "编译",
            "--",  # flag pattern
        ],
        "cli_workflow",
    ),
    (
        [
            "决策", "decision", "为什么", "why", "方案", "选型", "架构",
            "architecture", "选择", "choose", "理由", "rationale",
            "替代", "alternative", "权衡", "trade-off", "tradeoff",
            "设计", "design", "技术栈", "tech stack", "决定",
            "确认", "采用", "结论", "截止日期", "confirmed",
        ],
        "project_decision",
    ),
    (
        [
            "偏好", "preference", "习惯", "habit", "默认", "default",
            "喜欢", "prefer", "平时", "usually", "风格", "style",
            "个人", "personal", "routine", "例行",
        ],
        "personal_preference",
    ),
    (
        [
            "提醒", "remind", "团队", "team", "关键", "critical",
            "合规", "compliance", "过期", "expir", "复习", "review",
            "风险", "risk", "api key", "截止", "deadline", "遗忘",
            "forget", "保留", "retain", "长期记住", "团队记住",
            "不要忘", "请记录", "客户要求", "客户偏好", "密钥",
            "竞品", "remember", "retention",
        ],
        "team_retention",
    ),
]

_CLASSIFY_SYSTEM_PROMPT = """\
You are a domain classifier for a memory system.
Classify the input into exactly one of these four labels:
cli_workflow
project_decision
personal_preference
team_retention

Labels:
- cli_workflow: shell commands, build, deploy, troubleshooting workflows, terminal.
- project_decision: decisions, choices, rationales, architecture or technical selection.
- personal_preference: user habits, preferences, defaults, personal style.
- team_retention: facts a team must remember, risks, compliance, deadlines, customer requirements.

Only output the label. Do not output JSON, explanations, punctuation, or extra text.
"""


@dataclass(slots=True)
class ClassifyResult:
    primary: list[str] = field(default_factory=list)
    secondary: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.5
    method: str = "keyword_rule"
    reason: str = ""


class DomainClassifier:

    def __init__(self, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

    # ------------------------------------------------------------------
    # sync entry (for Router)
    # ------------------------------------------------------------------

    def classify_sync(
        self,
        text: str,
        *,
        event_type: str | None = None,
    ) -> ClassifyResult:
        hard = self._hard_rule(text, event_type)
        if hard is not None:
            return hard

        if self.llm_client is not None:
            try:
                return _run_async(self._llm_classify(text))
            except Exception:
                logger.debug(
                    "action=classify_sync_llm_failed fallback=keyword_rule"
                )

        return self._keyword_classify(text)

    # ------------------------------------------------------------------
    # async entry (for IntentAnalyzer)
    # ------------------------------------------------------------------

    async def classify(
        self,
        text: str,
        *,
        event_type: str | None = None,
    ) -> ClassifyResult:
        hard = self._hard_rule(text, event_type)
        if hard is not None:
            return hard

        if self.llm_client is not None:
            try:
                return await self._llm_classify(text)
            except Exception:
                logger.debug(
                    "action=classify_llm_failed fallback=keyword_rule"
                )

        return self._keyword_classify(text)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _hard_rule(self, text: str, event_type: str | None) -> ClassifyResult | None:
        if event_type in ("command_finished", "command_failed"):
            return ClassifyResult(
                primary=["cli_workflow"],
                secondary=_SECONDARY_AFFINITY["cli_workflow"],
                confidence=0.9,
                method="event_type_rule",
                reason="command event",
            )
        return None

    async def _llm_classify(self, text: str) -> ClassifyResult:
        label = await self.llm_client.atext(  # type: ignore[union-attr]
            _CLASSIFY_SYSTEM_PROMPT,
            text,
            temperature=0,
            max_tokens=16,
        )
        domain = self._parse_label(label.strip())
        keywords = self._match_keywords(text)
        return ClassifyResult(
            primary=[domain],
            secondary=_SECONDARY_AFFINITY[domain],
            keywords=keywords,
            confidence=0.8,
            method="llm",
            reason="llm classified",
        )

    def _match_keywords(self, text: str) -> list[str]:
        lowered = text.lower()
        matched: list[str] = []
        for keywords, _domain in _KEYWORD_RULES:
            for kw in keywords:
                if kw.lower() in lowered and kw not in matched:
                    matched.append(kw)
        return matched[:10]

    def _keyword_classify(self, text: str) -> ClassifyResult:
        lowered = text.lower()
        scores: dict[str, int] = {d: 0 for d in ALL_DOMAINS}
        for keywords, domain in _KEYWORD_RULES:
            for kw in keywords:
                if kw.lower() in lowered:
                    scores[domain] += 1

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary: list[str] = []
        secondary: list[str] = []

        if ranked[0][1] > 0:
            primary.append(ranked[0][0])
            if ranked[1][1] > 0 and ranked[1][1] >= ranked[0][1] * 0.5:
                primary.append(ranked[1][0])
        else:
            primary.append("team_retention")
            secondary.append("project_decision")

        if not secondary:
            for p in primary:
                for d in _SECONDARY_AFFINITY.get(p, []):  # type: ignore[arg-type]
                    if d not in primary and d not in secondary:
                        secondary.append(d)

        matched = [kw for kws, _ in _KEYWORD_RULES for kw in kws if kw.lower() in lowered]
        max_score = ranked[0][1] if ranked[0][1] > 0 else 0
        confidence = min(0.3 + max_score * 0.1, 0.8)

        return ClassifyResult(
            primary=primary,
            secondary=secondary,
            keywords=matched[:10],
            confidence=confidence,
            method="keyword_rule",
            reason="keyword matched",
        )

    @staticmethod
    def _parse_label(label: str) -> DomainLabel:
        label_lower = label.lower()
        for domain in ALL_DOMAINS:
            if domain in label_lower:
                return domain
        raise ValueError(f"invalid domain label: {label!r}")


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError(
        "DomainClassifier sync API cannot run inside an active event loop"
    )
