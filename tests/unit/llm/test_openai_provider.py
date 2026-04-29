from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm import openai_provider
from src.llm.base import ValidationError
from src.llm.openai_provider import OpenAIProvider
from src.schemas import Message, ProviderConfig


class FakeCompletions:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.response


class FakeAsyncOpenAI:
    last_instance: "FakeAsyncOpenAI | None" = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.completions = FakeCompletions(_fake_response())
        self.chat = SimpleNamespace(completions=self.completions)
        FakeAsyncOpenAI.last_instance = self


def _fake_response() -> SimpleNamespace:
    """Build the minimal OpenAI SDK response shape used by OpenAIProvider."""

    message = SimpleNamespace(content="hello", tool_calls=None)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    return SimpleNamespace(choices=[choice], model="sdk-model", usage=usage)


def test_openai_provider_sends_chat_completion_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_provider, "HAS_OPENAI", True)
    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)

    provider = OpenAIProvider(
        ProviderConfig(
            api_key="test-key",
            model="memory-model",
            base_url="https://example.test/v1",
            default_headers={"x-test": "1"},
            extra_body={"seed": 42},
        )
    )

    response = asyncio.run(
        provider.acomplete(
            [Message.system("sys"), Message.user("hi")],
            temperature=0.1,
            max_tokens=64,
            response_format={"type": "json_object"},
        )
    )

    assert response.content == "hello"
    assert response.model == "sdk-model"
    assert response.finish_reason == "stop"
    assert response.usage is not None
    assert response.usage.total_tokens == 5

    fake_client = FakeAsyncOpenAI.last_instance
    assert fake_client is not None
    assert fake_client.kwargs["api_key"] == "test-key"
    assert fake_client.kwargs["base_url"] == "https://example.test/v1"
    assert fake_client.kwargs["default_headers"] == {"x-test": "1"}

    request = fake_client.completions.requests[0]
    assert request["model"] == "memory-model"
    assert request["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert request["temperature"] == 0.1
    assert request["max_tokens"] == 64
    assert request["response_format"] == {"type": "json_object"}
    assert request["seed"] == 42


def test_openai_provider_extracts_choice_message_content() -> None:
    provider = object.__new__(OpenAIProvider)

    response = provider._parse_response(_fake_response(), "fallback-model")

    assert response.content == "hello"
    assert response.model == "sdk-model"


def test_openai_provider_uses_json_schema_for_generic_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_provider, "HAS_OPENAI", True)
    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)

    provider = OpenAIProvider(
        ProviderConfig(
            api_key="test-key",
            model="memory-model",
            base_url="https://example.test/v1",
        )
    )

    response_format = provider.json_response_format({"type": "object"})

    assert response_format is not None
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "larkmemory_schema"


def test_openai_provider_uses_json_object_for_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_provider, "HAS_OPENAI", True)
    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)

    provider = OpenAIProvider(
        ProviderConfig(
            api_key="test-key",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
        )
    )

    assert provider.is_deepseek_compatible is True
    assert provider.json_response_format({"type": "object"}) == {"type": "json_object"}
    assert provider.json_response_format(None) == {"type": "json_object"}


def test_openai_provider_requires_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_provider, "HAS_OPENAI", True)
    monkeypatch.setattr(openai_provider, "AsyncOpenAI", FakeAsyncOpenAI)

    provider = OpenAIProvider(ProviderConfig(api_key="test-key"))

    with pytest.raises(ValidationError) as exc_info:
        asyncio.run(provider.acomplete([Message.user("hi")]))

    assert "Model is required" in str(exc_info.value)
    assert exc_info.value.provider == "openai"
