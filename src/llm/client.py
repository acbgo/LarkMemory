from __future__ import annotations

import json
from typing import Any

from .openai_provider import OpenAIProvider
from src.schemas import LLMResponse, Message, ProviderConfig


class LLMClient:
    def __init__(self, provider: OpenAIProvider) -> None:
        self.provider = provider

    @classmethod
    def from_openai_compatible(
        cls,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        default_headers: dict[str, str] | None = None,
        extra_body: dict[str, Any] | None = None,
    ) -> "LLMClient":
        provider = OpenAIProvider(
            ProviderConfig(
                api_key=api_key,
                model=model,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries,
                default_headers=default_headers or {},
                extra_body=extra_body or {},
            )
        )
        return cls(provider)

    async def achat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return await self.provider.acomplete(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            **kwargs,
        )

    async def atext(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        messages: list[Message] = []
        if system_prompt:
            messages.append(Message.system(system_prompt))
        messages.append(Message.user(user_prompt))

        response = await self.achat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.content or ""

    async def ajson(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        temperature: float | None = 0,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response_format = None
        if schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "larkmemory_schema",
                    "schema": schema,
                },
            }

        content = await self.atext(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **kwargs,
        )
        return json.loads(content)
