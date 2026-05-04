from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class FeishuDocClientProtocol(Protocol):
    """文档 API 调用协议，方便测试时 mock。"""

    def fetch_doc_content(self, doc_token: str) -> str:
        """拉取文档全文（Markdown 格式）。"""
        ...


class FeishuDocClient:
    """基于 lark-oapi SDK 的文档 API 客户端。"""

    def __init__(self, api_client: Any) -> None:
        self._client = api_client

    def fetch_doc_content(self, doc_token: str) -> str:
        """调用 docx API 导出文档为 Markdown。"""
        from lark_oapi.api.docx.v1 import RawContentDocumentRequest  # type: ignore[import-not-found]

        request = RawContentDocumentRequest.builder().document_id(doc_token).build()
        response = self._client.docx.v1.document.raw_content(request)
        if not response.success():
            raise RuntimeError(
                f"Failed to fetch doc {doc_token}: "
                f"code={response.code} msg={response.msg}"
            )
        content = getattr(response.data, "content", None)
        return str(content) if content else ""
