from __future__ import annotations

import json
import logging
import os
import re
import shlex
from pathlib import Path
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


def _msys_to_windows_path(value: str) -> str:
    """Convert Git Bash style /c/... paths when the hook runs under Windows Python."""
    if len(value) >= 3 and value[0] == "/" and value[2] == "/":
        drive = value[1]
        if drive.isalpha():
            return f"{drive.upper()}:/{value[3:]}"
    return value


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

        command_name = self._normalize_command_identity(
            tokens,
            self._extract_base_command(tokens),
            cwd=str(event.payload.get("cwd") or ""),
        )

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
                command_name = self._normalize_command_identity(
                    tokens,
                    self._extract_base_command(tokens),
                    cwd=str(event.payload.get("cwd") or ""),
                )
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
                    rule_candidates[0].memory.command_template,
                    rule_candidates[0].memory.parameter_bindings,
                )
                if enriched:
                    rule_candidates[0].memory.parameter_bindings = enriched["parameter_bindings"]
                    rule_candidates[0].memory.semantic_description = enriched["semantic_description"]
                    rule_candidates[0].memory.scenario_keywords = enriched["scenario_keywords"]
                    rule_candidates[0].signals.append("llm_semantics")
                    logger.debug(
                        "action=llm_semantics_enriched command_template=%s command_name=%s "
                        "semantic_description=%s scenario_keywords=%s params=%s param_count=%s",
                        rule_candidates[0].memory.command_template,
                        rule_candidates[0].memory.command_name,
                        rule_candidates[0].memory.semantic_description,
                        rule_candidates[0].memory.scenario_keywords,
                        [
                            {
                                "param_name": pb.param_name,
                                "param_value": pb.param_value,
                                "semantics": pb.semantics,
                            }
                            for pb in rule_candidates[0].memory.parameter_bindings
                        ],
                        len(enriched["parameter_bindings"]),
                    )
            else:
                # 规则未命中 → LLM 完整提取
                llm_candidates = self._llm_full_extraction(text, event)
                if llm_candidates:
                    logger.debug("action=llm_full_extraction_done candidate_count=%s", len(llm_candidates))
                    return llm_candidates

        return rule_candidates

    def _build_openclaw_candidate(
        self,
        *,
        command_template: str,
        command_name: str,
        param_bindings: list[ParameterBinding],
        semantic_description: str | None = None,
        scenario_keywords: list[str] | None = None,
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
            semantic_description=semantic_description,
            scenario_keywords=scenario_keywords or [],
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

    def _normalize_command_identity(
        self,
        tokens: list[str],
        command_name: str,
        *,
        cwd: str = "",
    ) -> str:
        """将脚本类命令的执行文件路径归一成绝对路径，作为稳定 command identity。"""
        if len(tokens) < 2:
            return command_name
        executable = tokens[0]
        if executable.lower() not in {"python", "python3", "node", "deno", "bun"}:
            return command_name
        script = tokens[1]
        if script.startswith("-") or not self._looks_like_script_path(script):
            return command_name
        absolute_script = self._resolve_command_path(script, cwd=cwd)
        return f"{executable} {absolute_script}"

    @staticmethod
    def _looks_like_script_path(value: str) -> bool:
        lowered = value.lower()
        return (
            "/" in value
            or "\\" in value
            or lowered.endswith((".py", ".js", ".ts", ".mjs", ".cjs"))
        )

    @staticmethod
    def _resolve_command_path(value: str, *, cwd: str = "") -> str:
        normalized = _msys_to_windows_path(value).replace("/", os.sep)
        path = Path(normalized)
        if not path.is_absolute():
            normalized_cwd = _msys_to_windows_path(cwd or os.getcwd()).replace("/", os.sep)
            path = Path(normalized_cwd) / path
        try:
            return str(path.resolve())
        except OSError:
            return str(path.absolute())

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
            "intent": {"type": "string"},
            "semantic_description": {"type": "string"},
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
        },
    }

    _LLM_SEMANTICS_SYSTEM = (
        "你是一个 CLI 命令主动记忆抽取器。"
        "输入包含用户教学原文、已解析命令模板和参数绑定。"
        "请输出命令意图 intent、用于检索的中文 semantic_description、场景关键词 scenario_keywords，"
        "并为每个已解析参数补充简洁中文 semantics。"
        "不要新增原文或命令里不存在的参数；不知道就保留空字符串。"
        "只返回 JSON，不要输出任何其他内容。"
    )

    _LLM_EXTRACTION_SCHEMA: dict[str, Any] = {
        "type": "object",
        "required": ["scenario_keywords", "parameters", "is_teaching", "full_command"],
        "properties": {
            "full_command": {"type": "string|null"},
            "intent": {"type": "string"},
            "semantic_description": {"type": "string"},
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
         """
你是一个 CLI 工作流主动记忆场景中的命令教学语义分析器。

你的任务不是凭空生成命令，而是解析用户主动说出的自然语言记忆，将其中的命令、参数偏好、项目场景和命令意图转成结构化 JSON，供后续规则解析、检索和命令推荐使用。

你必须只输出一个 JSON 对象，不得输出 Markdown、解释文字、代码块或额外字段。输出必须严格符合给定 JSON Schema。

抽取原则：

1. full_command
- 如果用户文本中包含完整可执行命令，必须原样抽取到 full_command。
- 完整命令包括但不限于 shell、git、docker、kubectl、npm、pnpm、yarn、python、conda、ssh、scp、rsync、make、cmake、pytest、uv、pip 等命令。
- 不要改写、补全或美化命令。
- 不要猜测用户没有写出的命令。
- 如果用户没有给出完整命令，full_command 必须为 null。

2. is_teaching
- 如果用户是在主动教系统记住某个命令、参数偏好、项目路径、部署习惯或场景规则，设为 true。
- 典型表达包括：“记住”“以后”“下次”“部署 X 时用 Y”“在项目 A 里用这个参数”“默认用 staging”“这个项目走 xxx 命令”。
- 如果用户只是普通提问、闲聊、报错求助、一次性说明，且没有明确让系统沉淀为未来习惯，设为 false。
- 即使 is_teaching=false，也要根据输入尽量抽取已有语义字段。

3. intent
- 用简短短语概括命令或场景意图。
- 示例：部署项目、启动服务、运行测试、切换环境、构建镜像、同步文件、进入项目目录、查看日志、提交代码。
- 如果无法判断，填写空字符串 ""，不要编造。

4. semantic_description
- 用一句适合后续语义检索的中文描述表达该记忆。
- 应能支持用户未来用自然语言检索，例如“部署 demo-a”“staging 环境部署”“demo-a 项目启动服务”。
- 如果有 full_command，应说明该命令用于什么场景。
- 如果没有 full_command，应说明用户表达的命令偏好或参数语义。
- 不要写成泛泛总结。

5. scenario_keywords
- 提取与场景检索相关的关键词数组。
- 包括项目名、服务名、环境名、动作、工具名、路径、模块名等。
- 示例：["demo-a", "部署", "staging", "环境"]
- 不要放入无意义虚词。
- 如果无法提取，返回空数组 []。

6. parameters
- 只抽取用户明确提到的参数、参数值或偏好。
- 每个参数包含：
  - param_name：参数名、配置名或语义化参数名。
  - param_value：参数值。
  - semantics：该参数在命令场景中的含义。
- 如果用户给出了完整命令，可以抽取其中明确的参数，例如 --env staging、-p 8080:80。
- 如果用户只说“部署 demo-a 时 env 用 staging”，也应抽取 env=staging。
- 不要猜测未出现的参数。
- 如果没有参数，返回空数组 []。

低质量或非教学输入处理：
- 如果输入没有完整命令，也没有明确命令教学语义，full_command 为 null，is_teaching 为 false。
- 此时 intent 可以为空字符串，scenario_keywords 和 parameters 可以为空数组。
- semantic_description 应忠实说明输入缺少可沉淀的 CLI 工作流信息。

严格约束：
1. 只基于用户输入抽取，不得臆造命令、路径、参数或项目名。
2. 如果用户提供完整命令，full_command 必须尽量保持原文。
3. 如果用户没有完整命令，不得根据经验补全命令。
4. parameters 只记录明确出现的参数或偏好。
5. 输出必须是合法 JSON。
6. 不得输出 schema 之外的字段。
"""
    )

    def _llm_enrich_semantics(
        self,
        original_text: str,
        command_template: str,
        param_bindings: list[ParameterBinding],
    ) -> dict[str, Any] | None:
        """LLM 为规则已提取的 OpenClaw 命令补充命令语义和参数语义。"""
        try:
            raw = _run_async(
                self.llm_client.ajson(  # type: ignore[union-attr]
                    self._LLM_SEMANTICS_SYSTEM,
                    json.dumps(
                        {
                            "original_text": original_text,
                            "command_template": command_template,
                            "parameters": [
                                {"param_name": pb.param_name, "param_value": pb.param_value}
                                for pb in param_bindings
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    schema=self._LLM_SEMANTICS_SCHEMA,
                    temperature=0,
                    max_tokens=1024,
                )
            )
            llm_param_names = {str(item.get("param_name") or "") for item in raw.get("parameters", [])}
            rule_param_names = {pb.param_name for pb in param_bindings}
            if not llm_param_names & rule_param_names:
                return {
                    "parameter_bindings": param_bindings,
                    "semantic_description": clean_text(str(raw.get("semantic_description") or "")) or None,
                    "scenario_keywords": _string_list(raw.get("scenario_keywords")),
                }
            result: list[ParameterBinding] = []
            for pb in param_bindings:
                llm_item = next(
                    (item for item in raw.get("parameters", []) if str(item.get("param_name") or "") == pb.param_name),
                    None,
                )
                new_pb = ParameterBinding(
                    param_name=pb.param_name,
                    param_value=pb.param_value,
                    frequency=pb.frequency,
                    semantics=str(llm_item.get("semantics", "") or "") if llm_item else (pb.semantics or ""),
                )
                result.append(new_pb)
            return {
                "parameter_bindings": result,
                "semantic_description": clean_text(str(raw.get("semantic_description") or "")) or None,
                "scenario_keywords": _string_list(raw.get("scenario_keywords")),
            }
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
        semantic_description = clean_text(str(raw.get("semantic_description") or "")) or None
        logger.debug(
            "action=llm_full_extraction_raw is_teaching=%s full_command=%s "
            "semantic_description=%s scenario_keywords=%s params=%s",
            is_teaching,
            full_command,
            semantic_description,
            scenario_keywords,
            llm_params,
        )

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
                command_name = self._normalize_command_identity(
                    tokens,
                    self._extract_base_command(tokens),
                    cwd=str(event.payload.get("cwd") or ""),
                )
                command_template, parsed_bindings = self._parameterize(tokens, command_name)
                if command_template:
                    merged_bindings = _merge_parameter_semantics(parsed_bindings, param_bindings)
                    logger.debug(
                        "action=llm_full_extraction_candidate command_name=%s command_template=%s "
                        "semantic_description=%s scenario_keywords=%s params=%s",
                        command_name,
                        command_template,
                        semantic_description,
                        _string_list(scenario_keywords),
                        [
                            {
                                "param_name": pb.param_name,
                                "param_value": pb.param_value,
                                "semantics": pb.semantics,
                            }
                            for pb in merged_bindings
                        ],
                    )
                    return [
                        self._build_openclaw_candidate(
                            command_template=command_template,
                            command_name=command_name,
                            param_bindings=merged_bindings,
                            semantic_description=semantic_description,
                            scenario_keywords=_string_list(scenario_keywords),
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
                semantic_description=semantic_description,
                text=text,
                event=event,
            )

        return []

    def _associate_template(
        self,
        scenario_keywords: list[str],
        param_bindings: list[ParameterBinding],
        semantic_description: str | None,
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
                    semantic_description=semantic_description,
                    scenario_keywords=_string_list(scenario_keywords),
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
                    semantic_description=semantic_description,
                    scenario_keywords=_string_list(scenario_keywords),
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


def _string_list(value: Any) -> list[str]:
    """把 LLM 返回的数组字段规整成非空字符串列表。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        cleaned = clean_text(str(item))
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _merge_parameter_semantics(
    parsed_bindings: list[ParameterBinding],
    llm_bindings: list[ParameterBinding],
) -> list[ParameterBinding]:
    """以命令解析出的参数为准，仅用 LLM 结果补充参数语义。"""
    semantics_by_key = {
        (binding.param_name, binding.param_value): binding.semantics
        for binding in llm_bindings
        if binding.semantics
    }
    semantics_by_name = {
        binding.param_name: binding.semantics
        for binding in llm_bindings
        if binding.semantics
    }
    result: list[ParameterBinding] = []
    for binding in parsed_bindings:
        result.append(
            ParameterBinding(
                param_name=binding.param_name,
                param_value=binding.param_value,
                frequency=binding.frequency,
                semantics=(
                    semantics_by_key.get((binding.param_name, binding.param_value))
                    or semantics_by_name.get(binding.param_name)
                    or binding.semantics
                ),
            )
        )
    return result
