from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Role = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class FunctionCall:
    name: str
    arguments: str


@dataclass(slots=True)
class ToolCall:
    id: str
    function: FunctionCall
    type: str = "function"


@dataclass(slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class Message:
    role: Role
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None
    provider_specific: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls,
        content: str | None = None,
        *,
        tool_calls: list[ToolCall] | None = None,
    ) -> "Message":
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, content: str, tool_call_id: str) -> "Message":
        return cls(role="tool", content=content, tool_call_id=tool_call_id)


@dataclass(slots=True)
class LLMResponse:
    content: str | None
    model: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    tool_calls: list[ToolCall] | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(slots=True)
class ProviderConfig:
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    max_retries: int = 2
    default_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)

