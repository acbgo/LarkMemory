from __future__ import annotations

import hashlib
import logging
import re
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
    """文档编辑处理编排：拉取全文 → hash 对比 → 切分 → 增量写入。"""

    def __init__(
        self,
        source_state_store: SourceStateStore,
        doc_client: FeishuDocClientProtocol,
        dispatcher: FeishuEventDispatcher,
        *,
        team_id: str | None = None,
    ) -> None:
        self._state = source_state_store
        self._doc = doc_client
        self._dispatch = dispatcher
        self._team_id = team_id

    def process_doc_changed(self, file_token: str) -> None:
        """后台线程入口，编排完整的文档处理链路。"""
        try:
            self._process(file_token)
        except Exception:
            logger.exception(
                "action=doc_processor_failed file_token=%s", file_token
            )
            self._state.mark_error(SOURCE_TYPE, file_token)

    def process_doc_changed_async(self, file_token: str) -> None:
        """在后台线程中异步处理文档，不阻塞 WebSocket 回调。"""
        thread = threading.Thread(
            target=self.process_doc_changed,
            args=(file_token,),
            daemon=True,
        )
        thread.start()

    # ---- 内部 ----

    def _process(self, file_token: str) -> None:
        content = self._doc.fetch_doc_content(file_token)
        if not content.strip():
            logger.info("action=doc_empty file_token=%s", file_token)
            self._state.upsert_state(
                SOURCE_TYPE, file_token,
                status="complete",
                last_hash="",
                metadata={"section_count": 0, "doc_title": ""},
            )
            return

        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        existing = self._state.get_state(SOURCE_TYPE, file_token)
        if existing and existing.get("last_hash") == new_hash:
            logger.info(
                "action=doc_unchanged file_token=%s hash=%s",
                file_token,
                new_hash[:12],
            )
            return

        doc_title = _extract_first_heading(content) or file_token

        sections = split_by_headings(content)
        if not sections:
            return

        for section in sections:
            event = doc_section_to_event(
                section.content,
                section.heading,
                section.chunk_id,
                file_token,
                doc_title,
                section.index,
                team_id=self._team_id,
            )
            try:
                self._dispatch.dispatch_normalized_event(event)
            except Exception:
                logger.warning(
                    "action=doc_dispatch_failed event_id=%s", event.event_id
                )

        self._state.upsert_state(
            SOURCE_TYPE,
            file_token,
            status="complete",
            last_hash=new_hash,
            metadata={"section_count": len(sections), "doc_title": doc_title},
        )
        logger.info(
            "action=doc_processed file_token=%s sections=%d",
            file_token,
            len(sections),
        )


def _extract_first_heading(markdown: str) -> str | None:
    m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    return m.group(1).strip() if m else None
