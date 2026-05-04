from __future__ import annotations

import logging
import time
from typing import Any

from src.storage.source_state_store import SourceStateStore

from ..client.vc_client import FeishuVcClientProtocol
from ..events.dispatcher import FeishuEventDispatcher
from ..events.meeting_normalizer import ingest_notes_to_events

logger = logging.getLogger(__name__)

SOURCE_TYPE = "feishu_vc"
MAX_ERROR_COUNT = 10
RETRY_INTERVAL_SECONDS = 120
MAX_RETRIES = 3


class MeetingScanner:
    """定时扫描 source_state_store 中未完成的会议，兜底处理 AI 产物未就绪或 WebSocket 事件丢失的情况。"""

    def __init__(
        self,
        source_state_store: SourceStateStore,
        vc_client: FeishuVcClientProtocol,
        dispatcher: FeishuEventDispatcher,
    ) -> None:
        self._state = source_state_store
        self._vc = vc_client
        self._dispatch = dispatcher

    def run(self) -> int:
        """扫描所有 pending 状态的会议，返回本次成功补处理的数量。"""
        records = self._state.list_pending(SOURCE_TYPE)
        processed = 0

        for record in records:
            meeting_id = record["external_id"]
            if record.get("error_count", 0) > MAX_ERROR_COUNT:
                logger.info(
                    "action=scanner_skip_dead_letter meeting_id=%s error_count=%s",
                    meeting_id,
                    record["error_count"],
                )
                continue

            try:
                if self._try_process(record):
                    processed += 1
            except Exception:
                logger.exception(
                    "action=scanner_process_failed meeting_id=%s", meeting_id
                )
                self._state.mark_error(SOURCE_TYPE, meeting_id)

        logger.info(
            "action=scanner_done scanned=%s processed=%s",
            len(records),
            processed,
        )
        return processed

    def _try_process(self, record: dict[str, Any]) -> bool:
        meeting_id = record["external_id"]
        metadata = record.get("metadata", {})
        minute_token = metadata.get("minute_token", "")
        topic = metadata.get("topic", "")

        if not minute_token:
            logger.warning(
                "action=scanner_no_minute_token meeting_id=%s", meeting_id
            )
            self._state.mark_error(SOURCE_TYPE, meeting_id)
            return False

        for attempt in range(MAX_RETRIES):
            try:
                notes = self._vc.get_meeting_notes(minute_token)
                if notes.summary or notes.verbatim_text:
                    self._dispatch_events(
                        ingest_notes_to_events(notes, meeting_id, topic)
                    )
                    self._state.mark_complete(SOURCE_TYPE, meeting_id)
                    logger.info(
                        "action=scanner_processed meeting_id=%s chapters=%d todos=%d attempt=%d",
                        meeting_id,
                        len(notes.chapters),
                        len(notes.todos),
                        attempt + 1,
                    )
                    return True

                logger.info(
                    "action=scanner_notes_empty meeting_id=%s attempt=%d",
                    meeting_id,
                    attempt + 1,
                )
            except Exception:
                logger.warning(
                    "action=scanner_notes_error meeting_id=%s attempt=%d",
                    meeting_id,
                    attempt + 1,
                    exc_info=True,
                )

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_INTERVAL_SECONDS)

        self._state.mark_error(SOURCE_TYPE, meeting_id)
        return False

    def _dispatch_events(self, events: list[Any]) -> None:
        for evt in events:
            try:
                self._dispatch.dispatch_normalized_event(evt)
            except Exception:
                logger.warning(
                    "action=scanner_dispatch_failed event_id=%s",
                    getattr(evt, "event_id", ""),
                )
