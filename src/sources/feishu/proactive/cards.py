from __future__ import annotations

from typing import Any


def build_review_reminder_card(suggestion: dict[str, Any]) -> dict[str, Any]:
    """Render a team-retention review suggestion as a Feishu interactive card."""
    memory_id = str(suggestion.get("memory_id") or "")
    risk_level = str((suggestion.get("metadata") or {}).get("risk_level") or "normal")
    due_at = suggestion.get("due_at") or "unknown"
    content = suggestion.get("content") or ""
    template = "red" if risk_level == "high" else "orange"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": "团队记忆复习提醒"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": f"**{content}**\n\n风险等级：{risk_level}\n\n到期时间：{due_at}",
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "已复习"},
                        "type": "primary",
                        "value": {
                            "source": "larkmemory",
                            "action": "reviewed",
                            "memory_id": memory_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "明天提醒"},
                        "value": {
                            "source": "larkmemory",
                            "action": "snooze",
                            "memory_id": memory_id,
                            "snooze_days": 1,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "废弃记忆"},
                        "type": "danger",
                        "value": {
                            "source": "larkmemory",
                            "action": "expire",
                            "memory_id": memory_id,
                        },
                    },
                ],
            },
        ],
    }
