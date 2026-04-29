from __future__ import annotations

import asyncio

import pytest

from src.llm.base import LLMJSONDecodeError, LLMProvider
from src.llm.client import LLMClient
from src.schemas import LLMResponse, Message


class FakeProvider(LLMProvider):
    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content
        self.calls: list[dict[str, object]] = []

    @property
    def provider_name(self) -> str:
        return "fake"

    async def _acomplete_impl(
        self,
        messages: list[Message],
        **kwargs: object,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return LLMResponse(content=self.content, model="fake-model")


class FakeJSONModeProvider(FakeProvider):
    def json_response_format(self, schema: dict[str, object] | None) -> dict[str, object] | None:
        return {"type": "json_object"}


def test_atext_builds_messages_and_returns_content() -> None:
    provider = FakeProvider("ok")
    client = LLMClient(provider)

    result = asyncio.run(
        client.atext(
            "system prompt",
            "user prompt",
            temperature=0.2,
            max_tokens=128,
        )
    )

    assert result == "ok"
    assert len(provider.calls) == 1

    call = provider.calls[0]
    messages = call["messages"]
    kwargs = call["kwargs"]

    assert isinstance(messages, list)
    assert messages[0].role == "system"
    assert messages[0].content == "system prompt"
    assert messages[1].role == "user"
    assert messages[1].content == "user prompt"
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 128


def test_ajson_parses_model_json_response() -> None:
    provider = FakeProvider('{"topic":"memory","score":0.9}')
    client = LLMClient(provider)

    result = asyncio.run(
        client.ajson(
            "extract json",
            "return structured output",
            schema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "score": {"type": "number"},
                },
                "required": ["topic", "score"],
            },
        )
    )

    assert result == {"topic": "memory", "score": 0.9}
    assert len(provider.calls) == 1

    call = provider.calls[0]
    kwargs = call["kwargs"]
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["name"] == "larkmemory_schema"


def test_ajson_uses_provider_json_object_mode() -> None:
    provider = FakeJSONModeProvider('{"should_extract":true}')
    client = LLMClient(provider)

    result = asyncio.run(
        client.ajson(
            "judge event",
            "return whether this should be extracted",
            schema={
                "type": "object",
                "properties": {"should_extract": {"type": "boolean"}},
            },
        )
    )

    assert result == {"should_extract": True}

    call = provider.calls[0]
    messages = call["messages"]
    kwargs = call["kwargs"]

    assert kwargs["response_format"] == {"type": "json_object"}
    assert isinstance(messages, list)
    assert messages[0].role == "system"
    assert "JSON" in (messages[0].content or "")


def test_ajson_uses_provider_json_object_mode_without_schema() -> None:
    provider = FakeJSONModeProvider('{"should_extract":true}')
    client = LLMClient(provider)

    result = asyncio.run(client.ajson("judge event", "return whether this should be extracted"))

    assert result == {"should_extract": True}
    assert provider.calls[0]["kwargs"]["response_format"] == {"type": "json_object"}


def test_ajson_wraps_invalid_json_response(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeProvider("not json")
    client = LLMClient(provider)

    with pytest.raises(LLMJSONDecodeError) as exc_info:
        asyncio.run(client.ajson(None, "return json"))

    assert "not valid JSON" in str(exc_info.value)
    assert exc_info.value.content == "not json"
    assert exc_info.value.cause is not None
    assert "function=src.llm.client.LLMClient.ajson action=json_decode_failed" in caplog.text
    assert "raw_content_preview='not json'" in caplog.text


def test_ajson_requires_json_object_response() -> None:
    provider = FakeProvider('["not","object"]')
    client = LLMClient(provider)

    with pytest.raises(LLMJSONDecodeError) as exc_info:
        asyncio.run(client.ajson(None, "return json object"))

    assert "must be an object" in str(exc_info.value)
    assert exc_info.value.content == '["not","object"]'
