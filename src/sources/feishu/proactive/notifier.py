from __future__ import annotations

import json
from typing import Any

from .cards import build_review_reminder_card


class FeishuNotifier:
    """Send text and interactive-card messages through a lark-oapi client."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def send_text(self, chat_id: str, text: str) -> Any:
        """Send a plain text message to a Feishu chat."""
        return self._create_message(chat_id, "text", json.dumps({"text": text}, ensure_ascii=False))

    def send_interactive_card(self, chat_id: str, card: dict[str, Any]) -> Any:
        """Send a Feishu interactive card to a chat."""
        return self._create_message(chat_id, "interactive", json.dumps(card, ensure_ascii=False))

    def send_review_reminder(self, chat_id: str, suggestion: dict[str, Any]) -> Any:
        """Render and send a team-retention review reminder card."""
        return self.send_interactive_card(chat_id, build_review_reminder_card(suggestion))

    def _create_message(self, chat_id: str, msg_type: str, content: str) -> Any:
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Missing optional dependency: install lark-oapi to send Feishu messages") from exc

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type(msg_type)
                .content(content)
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.create(request)
        if hasattr(response, "success") and not response.success():
            raise RuntimeError(f"Feishu message send failed: {response.code} {response.msg}")
        return response
