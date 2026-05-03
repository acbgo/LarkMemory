from __future__ import annotations

import json
import logging
import re
import shlex
from typing import Any

from src.schemas import NormalizedEvent
from src.utils.text import clean_text
from src.utils.time import utc_now_iso

from .models import CLIWorkflowCandidate, CLIWorkflowMemory, ParameterBinding


logger = logging.getLogger(__name__)

_TRIVIAL_COMMANDS: set[str] = {
    "cd", "ls", "ll", "dir", "pwd", "echo", "cat", "less", "more",
    "head", "tail", "clear", "exit", "man", "help", "which", "whoami",
    "date", "env", "printenv", "set", "unset", "export", "alias",
    "unalias", "type", "source", ".", "bg", "fg", "jobs", "kill",
    "wait", "disown", "ulimit", "umask", "history", "logout",
    "open", "start", "xdg-open",
}

_KNOWN_TOOLCHAINS: set[str] = {
    "git", "docker", "docker-compose", "kubectl", "k", "helm",
    "npm", "npx", "yarn", "pnpm", "bun", "node", "deno",
    "uv", "pip", "pip3", "python", "python3", "poetry",
    "go", "cargo", "rustc", "make", "cmake", "gradle", "mvn",
    "terraform", "tofu", "ansible", "ansible-playbook",
    "lark", "lark-cli", "curl", "wget", "ssh", "scp", "rsync",
    "gh", "glab", "gcloud", "aws", "az",
}


def _is_trivial(command_name: str) -> bool:
    base = command_name.split()[0].lower() if command_name else ""
    return base in _TRIVIAL_COMMANDS


def _has_known_prefix(command_name: str) -> bool:
    base = command_name.split()[0].lower() if command_name else ""
    return base in _KNOWN_TOOLCHAINS


def _has_flags(tokens: list[str]) -> bool:
    return any(t.startswith("--") or (t.startswith("-") and len(t) == 2) for t in tokens)


class CLIWorkflowExtractor:
    """从 shell 或 openclaw 事件中提取 CLI 工作流记忆。"""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        memory_store: Any | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.memory_store = memory_store

    def extract(self, event: NormalizedEvent) -> list[CLIWorkflowCandidate]:
        text = self._collect_text(event)
        if not text:
            return []

        source_type = event.source_type
        if source_type == "shell":
            return self._extract_shell(text, event)
        if source_type == "openclaw":
            return self._extract_openclaw(text, event)
        return []

    def _collect_text(self, event: NormalizedEvent) -> str:
        parts: list[str] = []
        if event.content_text:
            parts.append(event.content_text)
        if event.title:
            parts.append(event.title)
        return clean_text(" ".join(parts))

    def _extract_shell(self, text: str, event: NormalizedEvent) -> list[CLIWorkflowCandidate]:
        tokens = self._tokenize(text)
        if not tokens:
            return []

        command_name = self._extract_base_command(tokens)

        if _is_trivial(command_name):
            return []

        has_flags = _has_flags(tokens)
        has_known_prefix = _has_known_prefix(command_name)

        if not has_flags and not has_known_prefix:
            return []

        if has_known_prefix and len(tokens) == 1:
            return []

        command_template, param_bindings = self._parameterize(tokens, command_name)
        if not command_template:
            return []

        exit_code = event.payload.get("exit_code", 0)
        success = exit_code == 0 if exit_code is not None else True
        category = self._infer_category(command_name)
        user_id = event.context.user_id or ""
        project_id = event.context.project_id
        repo_id = event.context.repo_id

        memory = CLIWorkflowMemory(
            user_id=user_id,
            command_template=command_template,
            command_name=command_name,
            command_category=category,
            project_id=project_id,
            repo_id=repo_id,
            parameter_bindings=param_bindings,
            execution_count=1,
            last_executed_at=event.occurred_at or utc_now_iso(),
            success_count=1 if success else 0,
            source_type="shell",
            source_event_id=event.event_id,
        )

        signals = ["rule_shell_extraction"]
        if has_flags:
            signals.append("has_flags")
        if has_known_prefix:
            signals.append("known_toolchain")

        return [CLIWorkflowCandidate(memory=memory, evidence_text=text, signals=signals)]

    def _extract_openclaw(self, text: str, event: NormalizedEvent) -> list[CLIWorkflowCandidate]:
        """从 OpenClaw 显式教学中提取命令记忆。

        规则优先（零延迟），LLM 补语义或做完整提取。
        - 规则命中（引号命令 / 已知工具链）：LLM 补充参数语义描述
        - 规则未命中（场景词+参数片段）：LLM 完整提取 + 关联已有模板
        """
        quoted_command = self._extract_quoted_command(text)
        inferred_command = self._infer_command_from_text(text) if not quoted_command else None

        rule_hit = bool(quoted_command or inferred_command)
        rule_candidates: list[CLIWorkflowCandidate] = []

        raw_command = quoted_command or inferred_command or ""
        if raw_command:
            tokens = self._tokenize(raw_command)
            if tokens:
                command_name = self._extract_base_command(tokens)
                command_template, param_bindings = self._parameterize(tokens, command_name)
                if command_template:
                    signals = ["openclaw_explicit"]
                    if quoted_command:
                        signals.append("quoted_command")
                    else:
                        signals.append("inferred_command")
                    rule_candidates = [
                        self._build_openclaw_candidate(
                            command_template=command_template,
                            command_name=command_name,
                            param_bindings=param_bindings,
                            text=text,
                            event=event,
                            evidence=raw_command,
                            signals=signals,
                            needs_review=not bool(quoted_command),
                        )
                    ]

        # ── LLM 路径 ──
        if self.llm_client is not None:
            if rule_hit and rule_candidates:
                # 规则命中 → LLM 仅补语义
                enriched = self._llm_enrich_semantics(
                    text,
                    rule_candidates[0].memory.parameter_bindings,
                )
                if enriched:
                    rule_candidates[0].memory.parameter_bindings = enriched
                    rule_candidates[0].signals.append("llm_semantics")
                    logger.info("action=llm_semantics_enriched param_count=%s", len(enriched))
            else:
                # 规则未命中 → LLM 完整提取
                llm_candidates = self._llm_full_extraction(text, event)
                if llm_candidates:
                    logger.info("action=llm_full_extraction_done candidate_count=%s", len(llm_candidates))
                    return llm_candidates

        return rule_candidates

    def _build_openclaw_candidate(
        self,
        *,
        command_template: str,
        command_name: str,
        param_bindings: list[ParameterBinding],
        text: str,
        event: NormalizedEvent,
        evidence: str,
        signals: list[str],
        needs_review: bool = False,
    ) -> CLIWorkflowCandidate:
        category = self._infer_category(command_name)
        memory = CLIWorkflowMemory(
            user_id=event.context.user_id or "",
            command_template=command_template,
            command_name=command_name,
            command_category=category,
            project_id=event.context.project_id,
            repo_id=event.context.repo_id,
            parameter_bindings=param_bindings,
            execution_count=1,
            last_executed_at=event.occurred_at or utc_now_iso(),
            success_count=1,
            source_type="openclaw",
            source_event_id=event.event_id,
        )
        return CLIWorkflowCandidate(
            memory=memory,
            evidence_text=evidence,
            signals=signals,
            needs_review=needs_review,
        )

    def _tokenize(self, text: str) -> list[str]:
        try:
            tokens = shlex.split(text)
        except ValueError:
            tokens = text.split()
        return [t for t in tokens if t.strip()]

    def _extract_base_command(self, tokens: list[str]) -> str:
        """提取基础命令名：第一个 -- 或 -x 标志之前的部分。"""
        base: list[str] = []
        for token in tokens:
            if token.startswith("--") or (token.startswith("-") and len(token) == 2):
                break
            if token.startswith("-"):
                break
            base.append(token)
            if len(base) >= 3:
                break
        return " ".join(base) if base else ""

    def _parameterize(
        self, tokens: list[str], command_name: str
    ) -> tuple[str, list[ParameterBinding]]:
        """将 token 列表参数化，返回 (模板字符串, 参数绑定列表)。"""
        cmd_parts = command_name.split()
        remaining = tokens[len(cmd_parts):]

        template_parts = list(cmd_parts)
        bindings: list[ParameterBinding] = []
        positional_index = 0

        i = 0
        while i < len(remaining):
            token = remaining[i]
            if token.startswith("--"):
                name = token[2:].split("=", 1)
                if len(name) == 2:
                    # --key=value
                    param_name = name[0]
                    param_value = name[1]
                    template_parts.append(f"--{param_name}={{{param_name}}}")
                    bindings.append(ParameterBinding(param_name=param_name, param_value=param_value))
                elif i + 1 < len(remaining) and not remaining[i + 1].startswith("-"):
                    # --key value
                    param_name = name[0]
                    param_value = remaining[i + 1]
                    template_parts.append(f"--{param_name} {{{param_name}}}")
                    bindings.append(ParameterBinding(param_name=param_name, param_value=param_value))
                    i += 1
                else:
                    # --flag (boolean)
                    template_parts.append(token)
                i += 1
            elif token.startswith("-") and len(token) == 2:
                if i + 1 < len(remaining) and not remaining[i + 1].startswith("-"):
                    param_name = token[1:]
                    param_value = remaining[i + 1]
                    template_parts.append(f"-{param_name} {{{param_name}}}")
                    bindings.append(ParameterBinding(param_name=param_name, param_value=param_value))
                    i += 1
                else:
                    template_parts.append(token)
                i += 1
            else:
                positional_index += 1
                param_name = f"arg{positional_index}"
                template_parts.append(f"{{{param_name}}}")
                bindings.append(ParameterBinding(param_name=param_name, param_value=token))
                i += 1

        template = " ".join(template_parts)
        return template, bindings

    def _infer_category(self, command_name: str) -> str:
        base = command_name.split()[0].lower() if command_name else ""
        category_map: dict[str, str] = {
            "git": "vcs", "gh": "vcs", "glab": "vcs",
            "docker": "container", "docker-compose": "container",
            "kubectl": "orchestration", "k": "orchestration", "helm": "orchestration",
            "npm": "package", "npx": "package", "yarn": "package",
            "pnpm": "package", "bun": "package", "uv": "package",
            "pip": "package", "pip3": "package", "poetry": "package",
            "go": "build", "cargo": "build", "rustc": "build",
            "make": "build", "cmake": "build", "gradle": "build", "mvn": "build",
            "terraform": "iac", "tofu": "iac", "ansible": "iac",
            "lark": "lark", "lark-cli": "lark",
            "curl": "network", "wget": "network", "ssh": "network",
            "gcloud": "cloud", "aws": "cloud", "az": "cloud",
            "python": "script", "python3": "script", "node": "script",
        }
        return category_map.get(base, "general")

    def _extract_quoted_command(self, text: str) -> str | None:
        """从自然语言文本中提取被引号包裹的命令字符串。"""
        patterns = [
            r'"([^"]+)"',
            r"'([^']+)'",
            r'`([^`]+)`',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                cleaned = clean_text(match)
                if cleaned and any(
                    cleaned.startswith(prefix)
                    for prefix in _KNOWN_TOOLCHAINS
                ):
                    return cleaned
        return None

    def _infer_command_from_text(self, text: str) -> str | None:
        """从自然语言中尝试推断命令。"""
        words = text.split()
        for i, word in enumerate(words):
            lowered = word.lower().strip("，。！？,.!?;；：:")
            if lowered in _KNOWN_TOOLCHAINS:
                remaining = words[i + 1:i + 10]
                return " ".join([word] + remaining)
        return None

    # ── LLM helpers ────────────────────────────────────────────────────────

    _LLM_SEMANTICS_SCHEMA: dict[str, Any] = {
        "type": "object",
        "required": ["parameters"],
        "properties": {
            "parameters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["param_name", "param_value", "semantics"],
                    "properties": {
                        "param_name": {"type": "string"},
                        "param_value": {"type": "string"},
                        "semantics": {"type": "string"},
                    },
                },
            },
        },
    }

    _LLM_SEMANTICS_SYSTEM = (
        "你是一个 CLI 命令参数语义分析器。"
        "输入是一组已被解析的参数绑定和用户教学原文。"
        "为每个参数补充一段简洁的中文语义解释（semantics 字段），说明该参数在当前场景下的含义。"
        "只返回 JSON，不要输出任何其他内容。"
    )

    _LLM_EXTRACTION_SCHEMA: dict[str, Any] = {
        "type": "object",
        "required": ["scenario_keywords", "parameters", "is_teaching", "full_command"],
        "properties": {
            "full_command": {"type": "string|null"},
            "scenario_keywords": {
                "type": "array",
                "items": {"type": "string"},
            },
            "parameters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["param_name", "param_value", "semantics"],
                    "properties": {
                        "param_name": {"type": "string"},
                        "param_value": {"type": "string"},
                        "semantics": {"type": "string"},
                    },
                },
            },
            "is_teaching": {"type": "boolean"},
        },
    }

    _LLM_EXTRACTION_SYSTEM = (
        "你是一个 CLI 工作流命令教学语义分析器。"
        "用户可能给出完整命令，也可能只描述场景和参数片段。"
        "如果用户给出了完整命令，请在 full_command 字段返回该命令。"
        "如果用户只描述了场景（如'部署时提醒我'），full_command 为 null，用 scenario_keywords 描述场景。"
        "parameters 中的每个参数必须包含语义解释（semantics）。"
        "is_teaching 表示用户意图是否为显式命令教学。"
        "只返回 JSON，不要输出 Markdown、解释文字或额外字段。"
    )

    def _llm_enrich_semantics(
        self,
        original_text: str,
        param_bindings: list[ParameterBinding],
    ) -> list[ParameterBinding] | None:
        """LLM 为规则已提取的参数补充语义描述。"""
        try:
            raw = _run_async(
                self.llm_client.ajson(  # type: ignore[union-attr]
                    self._LLM_SEMANTICS_SYSTEM,
                    json.dumps(
                        {
                            "original_text": original_text,
                            "parameters": [
                                {"param_name": pb.param_name, "param_value": pb.param_value}
                                for pb in param_bindings
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    schema=self._LLM_SEMANTICS_SCHEMA,
                    temperature=0,
                    max_tokens=512,
                )
            )
            result: list[ParameterBinding] = []
            for item in raw.get("parameters", []):
                pb = next(
                    (p for p in param_bindings if p.param_name == item.get("param_name")),
                    None,
                )
                if pb:
                    new_pb = ParameterBinding(
                        param_name=pb.param_name,
                        param_value=pb.param_value,
                        frequency=pb.frequency,
                        semantics=str(item.get("semantics", "") or ""),
                    )
                    result.append(new_pb)
            return result if result else None
        except Exception:
            logger.debug("action=llm_semantics_failed", exc_info=True)
            return None

    def _llm_full_extraction(
        self,
        text: str,
        event: NormalizedEvent,
    ) -> list[CLIWorkflowCandidate]:
        """LLM 完整提取：场景词 + 参数片段 → 关联已有模板 → 候选记忆。"""
        try:
            raw = _run_async(
                self.llm_client.ajson(  # type: ignore[union-attr]
                    self._LLM_EXTRACTION_SYSTEM,
                    json.dumps(
                        {"original_text": text},
                        ensure_ascii=False,
                    ),
                    schema=self._LLM_EXTRACTION_SCHEMA,
                    temperature=0,
                    max_tokens=1024,
                )
            )
        except Exception:
            logger.debug("action=llm_full_extraction_failed", exc_info=True)
            return []

        is_teaching = bool(raw.get("is_teaching"))
        if not is_teaching:
            return []

        llm_params = raw.get("parameters") or []
        scenario_keywords = raw.get("scenario_keywords") or []
        full_command = raw.get("full_command")

        if not llm_params and not full_command:
            return []

        param_bindings = [
            ParameterBinding(
                param_name=str(p.get("param_name", "")),
                param_value=str(p.get("param_value", "")),
                semantics=str(p.get("semantics", "") or ""),
            )
            for p in llm_params
            if p.get("param_name") and p.get("param_value")
        ]

        # 有完整命令 → 直接参数化
        if full_command:
            tokens = self._tokenize(str(full_command))
            if tokens:
                command_name = self._extract_base_command(tokens)
                command_template, _bindings = self._parameterize(tokens, command_name)
                if command_template:
                    return [
                        self._build_openclaw_candidate(
                            command_template=command_template,
                            command_name=command_name,
                            param_bindings=param_bindings,
                            text=text,
                            event=event,
                            evidence=str(full_command),
                            signals=["openclaw_explicit", "llm_full_extraction"],
                        )
                    ]

        # 无完整命令但有场景词 + 参数 → 关联已有模板
        if scenario_keywords and param_bindings:
            return self._associate_template(
                scenario_keywords=scenario_keywords,
                param_bindings=param_bindings,
                text=text,
                event=event,
            )

        return []

    def _associate_template(
        self,
        scenario_keywords: list[str],
        param_bindings: list[ParameterBinding],
        text: str,
        event: NormalizedEvent,
    ) -> list[CLIWorkflowCandidate]:
        """用场景词查同项目已有命令模板，绑定教过的参数。"""
        user_id = event.context.user_id or ""
        project_id = event.context.project_id

        existing_template: str | None = None
        existing_command_name: str | None = None

        if self.memory_store is not None and (user_id or project_id):
            try:
                filters: dict[str, str] = {}
                if user_id:
                    filters["user_id"] = user_id
                if project_id:
                    filters["project_id"] = project_id
                rows = self.memory_store.search_memory_candidates(
                    domain="cli_workflow",
                    status="active",
                    entity_filters=filters if filters else None,
                    limit=20,
                )
                for row in rows:
                    row_content = str(row.get("content_text", ""))
                    for kw in scenario_keywords:
                        if kw.lower() in row_content.lower():
                            existing = CLIWorkflowMemory.from_memory_core(row)
                            existing_template = existing.command_template
                            existing_command_name = existing.command_name
                            break
                    if existing_template:
                        break
            except Exception:
                logger.debug("action=template_association_failed", exc_info=True)

        if existing_template and existing_command_name:
            return [
                self._build_openclaw_candidate(
                    command_template=existing_template,
                    command_name=existing_command_name,
                    param_bindings=param_bindings,
                    text=text,
                    event=event,
                    evidence=text,
                    signals=["openclaw_explicit", "llm_full_extraction", "template_associated"],
                )
            ]

        # 找不到模板 → 创建待确认的候选记忆
        category = self._infer_category(scenario_keywords[0]) if scenario_keywords else "general"
        fallback_name = " ".join(scenario_keywords[:3]) if scenario_keywords else "unknown_command"
        return [
            CLIWorkflowCandidate(
                memory=CLIWorkflowMemory(
                    user_id=user_id,
                    command_template=fallback_name,
                    command_name=fallback_name,
                    command_category=category,
                    project_id=project_id,
                    repo_id=event.context.repo_id,
                    parameter_bindings=param_bindings,
                    execution_count=0,
                    source_type="openclaw",
                    source_event_id=event.event_id,
                ),
                evidence_text=text,
                signals=["openclaw_explicit", "llm_full_extraction", "partial_template"],
                needs_review=True,
            )
        ]


def _run_async(awaitable: Any) -> Any:
    try:
        import asyncio
        asyncio.get_running_loop()
    except RuntimeError:
        import asyncio
        return asyncio.run(awaitable)
    raise RuntimeError("CLIWorkflowExtractor sync API cannot run inside an active event loop")
