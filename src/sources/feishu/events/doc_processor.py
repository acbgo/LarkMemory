from __future__ import annotations

import hashlib
import logging
import threading
from typing import Any

from src.sources._shared.chunker import split_by_headings
from src.storage.source_state_store import SourceStateStore

from ..client.doc_client import FeishuDocClientProtocol
from .dispatcher import FeishuEventDispatcher
from .doc_normalizer import doc_section_to_event

logger = logging.getLogger(__name__)

SOURCE_TYPE = "feishu_doc"


class DocProcessor:
    """文档变更处理编排：拉取全文 → hash 对比 → 切分 → 增量写入。"""

    def __init__(
        self,
        source_state_store: SourceStateStore,
        doc_client: FeishuDocClientProtocol,
        dispatcher: FeishuEventDispatcher,
    ) -> None:
        self._state = source_state_store
        self._doc = doc_client
        self._dispatch = dispatcher

    def process_doc_changed(self, doc_token: str, doc_title: str | None = None) -> None:
        """后台线程入口，编排完整的文档处理链路。"""
        try:
            self._process(doc_token, doc_title)
        except Exception:
            logger.exception(
                "action=doc_processor_failed doc_token=%s", doc_token
            )
            self._state.mark_error(SOURCE_TYPE, doc_token)

    def process_doc_changed_async(
        self, doc_token: str, doc_title: str | None = None
    ) -> None:
        """在后台线程中异步处理文档，不阻塞 WebSocket 回调。"""
        thread = threading.Thread(
            target=self.process_doc_changed,
            args=(doc_token, doc_title),
            daemon=True,
        )
        thread.start()

    # ---- 内部 ----

    def _process(self, doc_token: str, doc_title: str | None) -> None:
        content = self._doc.fetch_doc_content(doc_token)
        if not content.strip():
            logger.info("action=doc_empty doc_token=%s", doc_token)
            return

        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = self._state.get_state(SOURCE_TYPE, doc_token)
        if existing and existing.get("last_hash") == new_hash:
            logger.info(
                "action=doc_unchanged doc_token=%s hash=%s",
                doc_token,
                new_hash[:12],
            )
            return

        sections = split_by_headings(content)
        if not sections:
            return

        for section in sections:
            event = doc_section_to_event(
                section.content,
                section.heading,
                doc_token,
                doc_title,
                section.index,
            )
            try:
                self._dispatch.dispatch_normalized_event(event)
            except Exception:
                logger.warning(
                    "action=doc_dispatch_failed event_id=%s", event.event_id
                )

        self._state.upsert_state(
            SOURCE_TYPE,
            doc_token,
            status="complete",
            last_hash=new_hash,
            metadata={"section_count": len(sections), "doc_title": doc_title or ""},
        )
        logger.info(
            "action=doc_processed doc_token=%s sections=%d",
            doc_token,
            len(sections),
        )
