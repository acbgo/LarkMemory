from __future__ import annotations

import logging
import time
import threading
from typing import Any

from src.sources._shared.chunker import split_by_chapters
from src.storage.source_state_store import SourceStateStore

from ..client.vc_client import FeishuVcClientProtocol
from .dispatcher import FeishuEventDispatcher
from .meeting_models import MeetingChapter, MeetingNotesData
from .meeting_normalizer import (
    meeting_chapter_to_event,
    meeting_summary_to_event,
    meeting_todo_to_event,
)

logger = logging.getLogger(__name__)

AI_GENERATION_DELAY_SECONDS = 300
RETRY_INTERVAL_SECONDS = 120
MAX_RETRIES = 5
SOURCE_TYPE = "feishu_vc"


class MeetingProcessor:
    """会议结束后的多步骤处理编排：获取妙记产物 → 切分 → 批量写入。"""

    def __init__(
        self,
        source_state_store: SourceStateStore,
        vc_client: FeishuVcClientProtocol,
        dispatcher: FeishuEventDispatcher,
    ) -> None:
        self._state = source_state_store
        self._vc = vc_client
        self._dispatch = dispatcher

    def process_meeting_ended(self, meeting_id: str, topic: str) -> None:
        """后台线程入口，编排完整的妙记处理链路。"""
        try:
            self._process(meeting_id, topic)
        except Exception:
            logger.exception(
                "action=meeting_processor_failed meeting_id=%s", meeting_id
            )
            self._state.mark_error(SOURCE_TYPE, meeting_id)

    def process_meeting_ended_async(self, meeting_id: str, topic: str) -> None:
        """在后台线程中异步处理会议，不阻塞 WebSocket 回调。"""
        thread = threading.Thread(
            target=self.process_meeting_ended,
            args=(meeting_id, topic),
            daemon=True,
        )
        thread.start()

    # ---- 内部 ----

    def _process(self, meeting_id: str, topic: str) -> None:
        existing = self._state.get_state(SOURCE_TYPE, meeting_id)
        if existing and existing.get("status") == "complete":
            logger.info(
                "action=meeting_already_processed meeting_id=%s", meeting_id
            )
            return

        self._state.upsert_state(SOURCE_TYPE, meeting_id, status="pending")

        minute_token = self._vc.get_recording(meeting_id)
        logger.info(
            "action=got_minute_token meeting_id=%s minute_token=%s",
            meeting_id,
            minute_token,
        )

        self._state.upsert_state(
            SOURCE_TYPE,
            meeting_id,
            status="pending_ai",
            metadata={"minute_token": minute_token, "topic": topic},
        )

        notes = self._fetch_notes_with_retry(minute_token)
        if notes is None:
            logger.warning(
                "action=notes_not_ready meeting_id=%s minute_token=%s",
                meeting_id,
                minute_token,
            )
            return

        self._ingest_notes(notes, meeting_id, topic)
        self._state.mark_complete(SOURCE_TYPE, meeting_id)
        logger.info(
            "action=meeting_processed meeting_id=%s chapters=%d todos=%d",
            meeting_id,
            len(notes.chapters),
            len(notes.todos),
        )

    def _fetch_notes_with_retry(self, minute_token: str) -> MeetingNotesData | None:
        time.sleep(AI_GENERATION_DELAY_SECONDS)

        for attempt in range(MAX_RETRIES):
            try:
                notes = self._vc.get_notes(minute_token)
                if notes.summary or notes.verbatim_text:
                    return notes
                logger.info(
                    "action=notes_empty attempt=%d minute_token=%s",
                    attempt + 1,
                    minute_token,
                )
            except Exception:
                logger.warning(
                    "action=notes_fetch_error attempt=%d minute_token=%s",
                    attempt + 1,
                    minute_token,
                    exc_info=True,
                )

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_INTERVAL_SECONDS)

        return None

    def _ingest_notes(
        self, notes: MeetingNotesData, meeting_id: str, topic: str
    ) -> None:
        events: list[Any] = []

        # 总结
        events.append(meeting_summary_to_event(notes, meeting_id, topic))

        # 待办
        for idx, todo in enumerate(notes.todos):
            events.append(
                meeting_todo_to_event(todo, meeting_id, notes.minute_token, idx)
            )

        # 章节
        chapter_dicts: list[dict[str, Any]] = [
            {"title": ch.title, "start_time_ms": ch.start_time_ms}
            for ch in notes.chapters
        ]
        for chunk in split_by_chapters(notes.verbatim_text, chapter_dicts):
            events.append(
                meeting_chapter_to_event(
                    chunk.content,
                    chunk.heading or f"章节 {chunk.index + 1}",
                    meeting_id,
                    notes.minute_token,
                    chunk.index,
                )
            )

        for evt in events:
            try:
                self._dispatch.dispatch_normalized_event(evt)
            except Exception:
                logger.warning(
                    "action=dispatch_failed event_id=%s", getattr(evt, "event_id", "")
                )
