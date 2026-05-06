from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import sqlite3

from src.core.service import IngestResult, MemoryService
from src.schemas import NormalizedEvent

from .models import FeishuMessageEvent
from .normalizer import normalize_message_event


logger = logging.getLogger(__name__)


class FeishuEventDispatcher:
    """Dispatch normalized Feishu source events into MemoryService."""

    def __init__(self, memory_service: MemoryService) -> None:
        self.memory_service = memory_service

    def dispatch_message(self, event: FeishuMessageEvent) -> IngestResult:
        """Normalize a Feishu message event and ingest it through MemoryService."""
        return self.dispatch_normalized_event(normalize_message_event(event))

    def dispatch_normalized_event(self, event: NormalizedEvent) -> IngestResult:
        """Ingest an already normalized Feishu event with duplicate-event tolerance."""
        try:
            return self._ingest_event_outside_running_loop(event)
        except sqlite3.IntegrityError:
            logger.info(
                "function=src.sources.feishu.events.dispatcher.FeishuEventDispatcher.dispatch_normalized_event action=duplicate event_id=%s",
                event.event_id,
            )
            return IngestResult(
                event_id=event.event_id,
                stored=True,
                message="duplicate feishu event ignored",
            )

    def _ingest_event_outside_running_loop(self, event: NormalizedEvent) -> IngestResult:
        """飞书 SDK 回调处于 asyncio loop 时，将同步 ingest 隔离到普通线程执行。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self.memory_service.ingest_event(event)

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="feishu-ingest") as executor:
            return executor.submit(self.memory_service.ingest_event, event).result()
