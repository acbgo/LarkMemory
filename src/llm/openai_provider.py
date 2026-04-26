from __future__ import annotations

import asyncio
import os
from typing import Any

from .base import (
    AuthenticationError,
    LLMProvider,
    ProviderError,
    RateLimitError,
    ValidationError,
)
from src.schemas import (
    FunctionCall,
    LLMResponse,
    Message,
    ProviderConfig,
    TokenUsage,
    ToolCall,
)

try:
    import openai
    from openai import AsyncOpenAI

    HAS_OPENAI = True
except ImportError:
    openai = None  # type: ignore[assignment]
    AsyncOpenAI = None  # type: ignore[assignment]
    HAS_OPENAI = False


class OpenAIProvider(LLMProvider):
    def __init__(self, config: ProviderConfig | None = None) -> None:
        super().__init__(config)

        if not HAS_OPENAI:
            raise ImportError("Missing dependency: openai")

        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise AuthenticationError(
                "API key is required for OpenAI-compatible providers.",
                provider="openai",
            )

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
            default_headers=self.config.default_headers or None,
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supports_tools(self) -> bool:
        return True

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {
                "role": message.role,
                "content": message.content,
            }
            if message.name:
                item["name"] = message.name
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tool.id,
                        "type": tool.type,
                        "function": {
                            "name": tool.function.name,
                            "arguments": tool.function.arguments,
                        },
                    }
                    for tool in message.tool_calls
                ]
            item.update(message.provider_specific)
            payload.append(item)
        return payload

    def _parse_response(self, response: Any, fallback_model: str) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] | None = None
        if getattr(message, "tool_calls", None):
            tool_calls = [
                ToolCall(
                    id=tool.id,
                    function=FunctionCall(
                        name=tool.function.name,
                        arguments=tool.function.arguments,
                    ),
                )
                for tool in message.tool_calls
            ]

        usage = None
        if getattr(response, "usage", None):
            usage = TokenUsage(
                prompt_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(response.usage, "total_tokens", 0) or 0,
            )

        raw_response = response.model_dump() if hasattr(response, "model_dump") else None
        return LLMResponse(
            content=getattr(message, "content", None),
            model=getattr(response, "model", None) or fallback_model,
            finish_reason=getattr(choice, "finish_reason", None),
            usage=usage,
            tool_calls=tool_calls,
            raw_response=raw_response,
        )

    def _handle_error(self, error: Exception) -> None:
        if openai is not None:
            if isinstance(error, openai.AuthenticationError):
                raise AuthenticationError(str(error), provider="openai", cause=error) from error
            if isinstance(error, openai.RateLimitError):
                raise RateLimitError(str(error), provider="openai", cause=error) from error
            if isinstance(error, (openai.BadRequestError, openai.NotFoundError)):
                raise ValidationError(str(error), provider="openai", cause=error) from error
        raise ProviderError(str(error), provider="openai", cause=error) from error

    async def _acomplete_impl(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        model_name = model or self.config.model
        if not model_name:
            raise ValidationError("Model is required.", provider="openai")

        request_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": self._convert_messages(messages),
        }
        if temperature is not None:
            request_kwargs["temperature"] = temperature
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        if tools:
            request_kwargs["tools"] = tools
        if tool_choice is not None:
            request_kwargs["tool_choice"] = tool_choice
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        if self.config.extra_body:
            request_kwargs.update(self.config.extra_body)
        request_kwargs.update(kwargs)

        try:
            response = await self._client.chat.completions.create(**request_kwargs)
            return self._parse_response(response, model_name)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._handle_error(error)
            raise
