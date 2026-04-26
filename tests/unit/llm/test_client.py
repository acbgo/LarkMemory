from __future__ import annotations

import asyncio

from src.llm.client import LLMClient
from src.schemas import LLMResponse, Message


class FakeProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def acomplete(self, messages: list[Message], **kwargs: object) -> LLMResponse:
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return LLMResponse(content=self.content, model="fake-model")


def test_atext_builds_messages_and_returns_content() -> None:
    provider = FakeProvider("ok")
    client = LLMClient(provider)  # type: ignore[arg-type]

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
    client = LLMClient(provider)  # type: ignore[arg-type]

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
