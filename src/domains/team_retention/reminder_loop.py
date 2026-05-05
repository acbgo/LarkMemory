from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_REMINDER_META_KEY = "reminder"
_TIMEOUT_HOURS = 24


class TeamRetentionReminderLoop:
    def __init__(
        self,
        memory_service: Any,
        notifier: Any,
        team_retention_store: Any,
        *,
        chat_id: str,
        interval_seconds: int = 3600,
    ) -> None:
        self.memory_service = memory_service
        self.notifier = notifier
        self.team_store = team_retention_store
        self.chat_id = chat_id
        self.interval = interval_seconds

    async def run(self) -> None:
        logger.info(
            "action=reminder_loop_start interval=%s chat_id=%s",
            self.interval,
            self.chat_id,
        )
        while True:
            try:
                await self._tick()
            except Exception:
                logger.warning("action=reminder_tick_failed", exc_info=True)
            await asyncio.sleep(self.interval)

    async def _tick(self) -> None:
        now = datetime.now(timezone.utc).isoformat()

        # ① 到期扫描 + 发送卡片 + 去重
        suggestions = self.memory_service.proactive_suggestions(
            team_id=None,
            project_id=None,
            workspace_id=None,
            limit=10,
            now=now,
            warning_window_hours=1,
        )
        sent_count = 0
        for suggestion in suggestions:
            memory_id = suggestion.get("memory_id")
            if not memory_id:
                continue
            memory = self.team_store.get_memory(memory_id)
            if memory is None:
                continue
            reminder_meta = (memory.metadata or {}).get(_REMINDER_META_KEY) or {}
            last_next = reminder_meta.get("last_next_review_at")
            if last_next and last_next == memory.next_review_at:
                continue  # same review cycle, already reminded

            try:
                self.notifier.send_review_reminder(self.chat_id, suggestion)
            except Exception:
                logger.warning(
                    "action=send_review_reminder_failed memory_id=%s",
                    memory_id,
                    exc_info=True,
                )
                continue

            new_meta = dict(memory.metadata or {})
            new_meta[_REMINDER_META_KEY] = {
                "last_sent_at": now,
                "last_next_review_at": memory.next_review_at,
            }
            self.team_store.update_memory_metadata(memory_id, new_meta)
            sent_count += 1
            logger.info(
                "action=review_reminder_sent memory_id=%s next_review=%s",
                memory_id,
                memory.next_review_at,
            )

        # ② 超时降级：超过 24 小时未响应 → candidate
        timed_out = 0
        active_rows = self.memory_service.memory_store.list_active_memories(
            domain="team_retention",
            limit=500,
        )
        for row in active_rows:
            memory = self.team_store.get_memory(row["memory_id"])
            if memory is None or memory.review_policy == "none":
                continue
            reminder_meta = (memory.metadata or {}).get(_REMINDER_META_KEY) or {}
            sent_at = reminder_meta.get("last_sent_at")
            if not sent_at:
                continue
            try:
                sent_dt = datetime.fromisoformat(sent_at)
            except ValueError:
                continue
            if datetime.now(timezone.utc) - sent_dt <= timedelta(hours=_TIMEOUT_HOURS):
                continue
            next_review = reminder_meta.get("last_next_review_at")
            if next_review and next_review != memory.next_review_at:
                continue  # reviewed — next_review_at changed, user responded

            self.memory_service.update_memory(
                action="forget", memory_id=memory.retention_id
            )
            self.team_store.update_memory_metadata(
                memory.retention_id,
                {
                    **(memory.metadata or {}),
                    "needs_confirmation": True,
                    "downgrade_reason": "review_reminder_timeout_24h",
                },
            )
            timed_out += 1
            logger.info(
                "action=memory_downgraded_candidate memory_id=%s reason=timeout_%sh",
                memory.retention_id,
                _TIMEOUT_HOURS,
            )

            try:
                self.notifier.send_interactive_card(
                    self.chat_id,
                    _build_downgrade_card(memory),
                )
            except Exception:
                logger.warning(
                    "action=downgrade_card_failed memory_id=%s",
                    memory.retention_id,
                    exc_info=True,
                )

        logger.info(
            "action=reminder_tick_done sent=%s timed_out=%s",
            sent_count,
            timed_out,
        )


def _build_downgrade_card(memory: Any) -> dict[str, Any]:
    fact_type = getattr(memory, "fact_type", "unknown")
    fact_value = getattr(memory, "fact_value", "")
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "yellow",
            "title": {"tag": "plain_text", "content": "团队记忆已降级为待确认"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**{fact_value}**\n\n"
                    f"类型：{fact_type}\n"
                    "该记忆的复习提醒已超过 24 小时未响应，已自动降级为待确认状态。\n"
                    "如需保留，请在记忆管理中手动确认。"
                ),
            },
        ],
    }
