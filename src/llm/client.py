from __future__ import annotations

import json
import logging
from typing import Any

from .base import LLMJSONDecodeError, LLMProvider
from .openai_provider import OpenAIProvider
from src.schemas import LLMResponse, Message, ProviderConfig


logger = logging.getLogger(__name__)


class LLMClient:
    """High-level LLM facade that delegates provider-specific calls to LLMProvider."""

    def __init__(self, provider: LLMProvider) -> None:
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
        """Forward a chat completion request to the configured provider."""

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
        """Build a prompt from system/user text and return response content."""

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
        """Return a JSON object or raise LLMJSONDecodeError with raw content."""

        response_format = self.provider.json_response_format(schema)
        if response_format and response_format.get("type") == "json_object":
            system_prompt, user_prompt = self._ensure_json_mode_prompt(
                system_prompt,
                user_prompt,
            )

        content = await self.atext(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **kwargs,
        )
        try:
            result = json.loads(content)
        except json.JSONDecodeError as error:
            logger.warning(
                "function=src.llm.client.LLMClient.ajson action=json_decode_failed content_length=%s raw_content_preview=%r",
                len(content),
                content,
            )
            raise LLMJSONDecodeError(
                "LLM response is not valid JSON.",
                content=content,
                cause=error,
            ) from error

        if not isinstance(result, dict):
            raise LLMJSONDecodeError(
                "LLM JSON response must be an object.",
                content=content,
            )
        return result

    @staticmethod
    def _ensure_json_mode_prompt(
        system_prompt: str | None,
        user_prompt: str,
    ) -> tuple[str | None, str]:
        """Ensure JSON-mode providers receive an explicit JSON instruction."""

        combined = f"{system_prompt or ''}\n{user_prompt}".lower()
        if "json" in combined:
            return system_prompt, user_prompt
        instruction = "Return only a valid JSON object."
        if system_prompt:
            return f"{system_prompt}\n{instruction}", user_prompt
        return instruction, user_prompt
