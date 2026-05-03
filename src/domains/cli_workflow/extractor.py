from __future__ import annotations

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

    def __init__(self, *, llm_client: Any | None = None) -> None:
        self.llm_client = llm_client

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

        支持两种自然语言模式：
        1. 包含引号命令: "lark project deploy --env staging --canary 50"
        2. key-value 教学: "部署用 --env staging，项目是后台服务"
        """
        quoted_command = self._extract_quoted_command(text)
        if quoted_command:
            tokens = self._tokenize(quoted_command)
            if tokens:
                command_name = self._extract_base_command(tokens)
                command_template, param_bindings = self._parameterize(tokens, command_name)
                if command_template:
                    category = self._infer_category(command_name)
                    user_id = event.context.user_id or ""
                    project_id = event.context.project_id
                    memory = CLIWorkflowMemory(
                        user_id=user_id,
                        command_template=command_template,
                        command_name=command_name,
                        command_category=category,
                        project_id=project_id,
                        repo_id=event.context.repo_id,
                        parameter_bindings=param_bindings,
                        execution_count=1,
                        last_executed_at=event.occurred_at or utc_now_iso(),
                        success_count=1,
                        source_type="openclaw",
                        source_event_id=event.event_id,
                    )
                    return [CLIWorkflowCandidate(
                        memory=memory,
                        evidence_text=quoted_command,
                        signals=["openclaw_explicit", "quoted_command"],
                    )]

        # Fallback: 尝试从自然语言中推断命令名
        inferred_command = self._infer_command_from_text(text)
        if inferred_command:
            tokens = self._tokenize(inferred_command)
            if tokens:
                command_name = self._extract_base_command(tokens)
                command_template, param_bindings = self._parameterize(tokens, command_name)
                if command_template:
                    category = self._infer_category(command_name)
                    user_id = event.context.user_id or ""
                    project_id = event.context.project_id
                    memory = CLIWorkflowMemory(
                        user_id=user_id,
                        command_template=command_template,
                        command_name=command_name,
                        command_category=category,
                        project_id=project_id,
                        repo_id=event.context.repo_id,
                        parameter_bindings=param_bindings,
                        execution_count=1,
                        last_executed_at=event.occurred_at or utc_now_iso(),
                        success_count=1,
                        source_type="openclaw",
                        source_event_id=event.event_id,
                    )
                    return [CLIWorkflowCandidate(
                        memory=memory,
                        evidence_text=inferred_command,
                        signals=["openclaw_explicit", "inferred_command"],
                        needs_review=True,
                    )]

        return []

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
