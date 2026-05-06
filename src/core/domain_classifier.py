from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from src.llm.base import LLMJSONDecodeError

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
            "脚本", "script", "pipeline",
            "kubectl", "npm", "pip", "pytest", "编译", # flag pattern
        ],
        "cli_workflow",
    ),
    (
        [
            "决定", "决策", "采用", "确认", "结论", "选择",
            "定下来", "敲定", "选定", "确定为",
            "同意", "通过", "批准", "否决", "驳回",
            "放弃", "不做", "改为", "换成",
            "拍板", "达成一致", "达成共识",
            "decision", "decided", "confirmed", "approved", "agreed",
            "finalized", "chosen", "rejected", "accepted",
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

Labels and boundaries:
- cli_workflow: shell commands, build/deploy steps, troubleshooting workflows, terminal usage.
- project_decision: project decisions, choices, rationales, architecture or technical selection, release/go-live decisions, rollback or hotfix decisions, budget/procurement decisions, owner assignments, migration decisions, API gateway or rate-limit decisions, incident handling conclusions.
- personal_preference: user habits, preferences, personal defaults, personal style. A project default such as default rate limits, default API threshold, or default rollout policy is not personal_preference.
- team_retention: facts a team must remember, risks, compliance, deadlines, customer requirements. Use this for durable team facts that are not project decisions.

Tie breakers:
- If a message contains scripts or commands but also contains decision markers such as conclusion, decision, approved release, rollback, grey rollout, owner assignment, or trade-off, classify project_decision over cli_workflow.
- If a message asks about current/default API thresholds, rate limits, budgets, rollout decisions, or incident conclusions, classify project_decision over personal_preference or team_retention.

Only output the label. Do not output JSON, explanations, punctuation, or extra text.
"""

_CLASSIFY_JSON_SYSTEM_PROMPT = """\
你是一个企业级长期记忆系统的事件路由分类器。你的任务是根据输入事件内容，判断该事件最适合进入哪一类记忆处理链路。

你必须只输出一个 JSON 对象，不得输出 Markdown、解释性文字、代码块或多余字段。输出必须严格符合以下字段：
- primary: 字符串，只能是 cli_workflow、project_decision、personal_preference、team_retention 四选一；
- confidence: 0 到 1 之间的数字，表示分类置信度；
- reason: 不超过 80 个字符的简短中文理由。

注意：即使输入是闲聊、噪声、无关内容或没有长期记忆价值，也必须在四个 primary 中选择最接近的一类，但 confidence 必须较低，并在 reason 中说明无明显记忆价值。后续系统会根据低 confidence 进行拒绝或忽略。

可选分类如下：

cli_workflow:
适用于开发者在终端、Shell、CLI、IDE、脚本执行、部署、调试、路径切换、环境配置等场景中的高频命令和工作流记忆。
典型事件包括：
- 高频长命令、复杂参数、项目路径；
- 某项目中反复使用特定命令组合；
- 用户主动说明“以后在项目 A 用这个部署参数”；
- 命令补全、参数推荐、路径偏好、工作流模板；
- git、docker、kubectl、npm、python、conda、ssh、scp、rsync、make、cmake 等命令习惯。

project_decision:
适用于飞书、项目群聊、会议纪要、文档评论、需求讨论中的项目决策与上下文记忆。
典型事件包括：
- 团队决定采用某方案、放弃某方案；
- 明确截止日期、负责人、里程碑、优先级；
- 记录决策理由、反对意见、风险、结论；
- 后续讨论需要引用历史决策；
- 与项目阶段、时间点、任务拆分、方案评审、需求变更相关的事件。

personal_preference:
适用于个人工作习惯、偏好、规律和自动化服务记忆。
典型事件包括：
- 用户偏好某种视图、格式、提醒方式、汇报方式；
- 用户经常在固定时间整理周报、准备会议材料；
- 用户主动表达“以后都这样做”“我更喜欢……”；
- 系统从点击、日程、命令、操作习惯中学习个人规律；
- 个性化建议、自动化执行、提醒、工作节奏优化相关事件。

team_retention:
适用于团队长期知识沉淀、遗忘预警、知识断层检测和版本覆盖记忆。
典型事件包括：
- API 密钥、接口规范、客户偏好、竞品动态等长期重要知识；
- 某些信息可能被团队遗忘，需要定期复习提醒；
- 知识过期、被新版本覆盖、需要废弃旧记忆；
- 团队成员变动导致上下文丢失；
- 团队共享知识、复习提醒、记忆覆盖、知识断层风险相关事件。
- FAQ人入职和日常开发需要知道的具体操作步骤，团建活动相关事件，旧服务器或环境配置相关事件，CI/CD 配置，安全漏洞详情。

分类原则：
1. 只选择一个最主要的 primary，且必须四选一,切记对于提问confidence应该小于0.20。
2. 如果事件是命令、路径、参数、终端工作流，优先选 cli_workflow。
3. 如果事件包含“决定、确认、采用、放弃、截止、负责人、方案、结论、原因、反对意见”，优先选 project_decision。
4. 如果事件主要体现个人偏好、个人习惯、个人提醒、个人自动化，优先选 personal_preference。
5. 如果事件主要体现团队长期知识、知识遗忘、知识覆盖、版本废弃、复习提醒，优先选 team_retention。
6. 如果事件同时涉及项目决策和团队知识沉淀：
   - 若重点是“当时做了什么决策”，选 project_decision；
   - 若重点是“长期保留、复习、防遗忘、版本覆盖”，选 team_retention。
7. 如果事件同时涉及个人偏好和 CLI 命令：
   - 若核心是命令推荐或参数补全，选 cli_workflow；
   - 若核心是个人偏好或自动化习惯，选 personal_preference。
8. 对于闲聊、情绪表达、无关文本、纯提问、泛泛讨论、没有可沉淀事实的事件：
   - 仍然必须选择四类中最接近的一类；
   - confidence 应低于 0.40；
   - reason 必须说明“无明显记忆价值”或“缺少可沉淀事实”。
9. 对于只有短期任务价值、但没有长期复用价值的事件：
   - confidence 通常应在 0.40-0.60；
   - 不要给出高置信度。
10. 置信度规则：
   - 0.90-1.00：事件明显属于单一记忆方向，且具有明确长期记忆价值；
   - 0.70-0.89：事件基本明确，有一定记忆价值，但存在轻微交叉；
   - 0.50-0.69：事件方向勉强可判定，或长期价值不强；
   - 0.20-0.49：闲聊、无关、噪声、纯提问、缺少可沉淀事实；
   - 低于 0.20：几乎无法判断或完全无效输入。
11. reason 必须简短说明判断依据，不超过 80 个字符。
12. 不要臆造输入中没有的信息。
13. 不要输出除 JSON 以外的任何内容。

输出示例：
{
  "primary": "project_decision",
  "confidence": 0.92,
  "reason": "事件包含项目方案选择和明确决策结论"
}

非记忆事件示例：
输入：“哈哈哈今天好累啊”
输出：
{
  "primary": "personal_preference",
  "confidence": 0.28,
  "reason": "仅为情绪表达，无明显记忆价值"
}

输入：“这个问题你怎么看？”
输出：
{
  "primary": "project_decision",
  "confidence": 0.35,
  "reason": "缺少具体项目事实或可沉淀结论"
}
"""

_CLASSIFY_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "primary": {
            "type": "string",
            "enum": ALL_DOMAINS,
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "reason": {
            "type": "string",
            "maxLength": 80,
        },
    },
    "required": ["primary", "confidence", "reason"],
    "additionalProperties": False,
}


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
        hard_result = self._hard_rule(text, event_type)
        if hard_result is not None:
            return hard_result

        kw_result = self._keyword_classify(text)
        if kw_result.confidence >= 0.5 and len(kw_result.keywords) >= 2:
            return kw_result

        if self.llm_client is not None:
            try:
                logger.info("action=classify_llm_start text_length=%s", len(text))
                return _run_async(self._llm_classify(text))
            except _LLMClassificationFallback as exc:
                logger.info(
                    "action=classify_sync_llm_rejected fallback=keyword_rule text_length=%s reason=%s",
                    len(text),
                    exc,
                )
            except Exception:
                logger.warning(
                    "action=classify_sync_llm_failed fallback=keyword_rule text_length=%s",
                    len(text),
                    exc_info=True,
                )

        return kw_result

    # ------------------------------------------------------------------
    # async entry (for IntentAnalyzer)
    # ------------------------------------------------------------------

    async def classify(
        self,
        text: str,
        *,
        event_type: str | None = None,
    ) -> ClassifyResult:
        hard_result = self._hard_rule(text, event_type)
        if hard_result is not None:
            return hard_result

        kw_result = self._keyword_classify(text)
        if kw_result.confidence >= 0.5 and len(kw_result.keywords) >= 2:
            return kw_result

        if self.llm_client is not None:
            try:
                logger.info("action=classify_llm_start text_length=%s", len(text))
                return await self._llm_classify(text)
            except _LLMClassificationFallback as exc:
                logger.info(
                    "action=classify_llm_rejected fallback=keyword_rule text_length=%s reason=%s",
                    len(text),
                    exc,
                )
            except Exception:
                logger.warning(
                    "action=classify_llm_failed fallback=keyword_rule text_length=%s",
                    len(text),
                    exc_info=True,
                )

        return kw_result

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
        if hasattr(self.llm_client, "ajson"):
            try:
                payload = await self.llm_client.ajson(  # type: ignore[union-attr]
                    _CLASSIFY_JSON_SYSTEM_PROMPT,
                    text,
                    schema=_CLASSIFY_JSON_SCHEMA,
                    temperature=0,
                    max_tokens=1024,
                )
                return self._parse_json_result(payload, text)
            except _LLMClassificationFallback:
                raise
            except LLMJSONDecodeError as exc:
                logger.info(
                    "action=classify_llm_json_decode_failed fallback=atext text_length=%s content_length=%s",
                    len(text),
                    len(exc.content or ""),
                )
            except Exception:
                logger.warning(
                    "action=classify_llm_json_failed fallback=atext text_length=%s",
                    len(text),
                    exc_info=True,
                )

        label = await self.llm_client.atext(  # type: ignore[union-attr]
            _CLASSIFY_SYSTEM_PROMPT,
            text,
            temperature=0,
            max_tokens=1024,
        )
        raw_label = str(label or "").strip()
        if not raw_label:
            logger.info("action=classify_llm_empty_output fallback=keyword_rule")
            raise _LLMClassificationFallback("empty llm classification output")
        try:
            domain = self._parse_label(raw_label)
        except ValueError:
            logger.info(
                "action=classify_llm_invalid_output fallback=keyword_rule raw=%r",
                raw_label,
            )
            raise _LLMClassificationFallback("invalid llm classification output")
        keywords = self._match_keywords(text)
        result = ClassifyResult(
            primary=[domain],
            secondary=_SECONDARY_AFFINITY[domain],
            keywords=keywords,
            confidence=0.8,
            method="llm",
            reason="llm classified",
        )
        logger.info(
            "action=classify_llm_done label=%s primary=%s secondary=%s keyword_count=%s confidence=%s",
            raw_label,
            result.primary,
            result.secondary,
            len(result.keywords),
            result.confidence,
        )
        return result

    def _parse_json_result(self, payload: Any, text: str) -> ClassifyResult:
        """解析 LLM 结构化分类结果；非法契约交给 keyword fallback 处理。"""

        if not isinstance(payload, dict):
            logger.info(
                "action=classify_llm_invalid_json fallback=keyword_rule raw_type=%s",
                type(payload).__name__,
            )
            raise _LLMClassificationFallback("llm json classification payload is not object")
        raw_primary = payload.get("primary") or payload.get("domain") or payload.get("label")
        try:
            domain = self._parse_label(str(raw_primary or "").strip())
        except ValueError:
            logger.info(
                "action=classify_llm_invalid_output fallback=keyword_rule raw=%r",
                raw_primary,
            )
            raise _LLMClassificationFallback("invalid llm json classification domain")
        raw_confidence = payload.get("confidence", 0.8)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.8
        confidence = max(0.0, min(1.0, confidence))
        reason = str(payload.get("reason") or "llm classified")
        result = ClassifyResult(
            primary=[domain],
            secondary=_SECONDARY_AFFINITY[domain],
            keywords=self._match_keywords(text),
            confidence=confidence,
            method="llm_json",
            reason=reason,
        )
        logger.info(
            "action=classify_llm_done label=%s primary=%s secondary=%s keyword_count=%s confidence=%s",
            domain,
            result.primary,
            result.secondary,
            len(result.keywords),
            result.confidence,
        )
        return result

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

        result = ClassifyResult(
            primary=primary,
            secondary=secondary,
            keywords=matched[:10],
            confidence=confidence,
            method="keyword_rule",
            reason="keyword matched",
        )
        logger.info(
            "action=classify_keyword_fallback_done primary=%s secondary=%s confidence=%s keyword_count=%s scores=%s",
            result.primary,
            result.secondary,
            result.confidence,
            len(result.keywords),
            scores,
        )
        return result

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


class _LLMClassificationFallback(Exception):
    """Expected LLM classification contract failure that should use keyword fallback."""
