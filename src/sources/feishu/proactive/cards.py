from __future__ import annotations

from typing import Any


def build_decision_context_card(suggestion: dict[str, Any]) -> dict[str, Any]:
    """Render a project-decision proactive suggestion as a Feishu interactive card."""
    memory_id = str(suggestion.get("memory_id") or "")
    title = str(suggestion.get("title") or suggestion.get("topic") or "相关历史决策")
    summary = str(suggestion.get("summary") or "")
    bullets = [str(item) for item in (suggestion.get("bullets") or []) if str(item).strip()]
    suggested_action = str(suggestion.get("suggested_action") or "查看历史决策上下文")
    bullet_text = "\n".join(f"- {item}" for item in bullets)
    content = f"**{title}**\n\n{summary}"
    if bullet_text:
        content = f"{content}\n\n相关历史：\n{bullet_text}"
    content = f"{content}\n\n建议：{suggested_action}"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "相关历史决策"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": content,
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "收到"},
                        "type": "primary",
                        "value": {
                            "source": "larkmemory",
                            "action": "reviewed",
                            "memory_id": memory_id,
                        },
                    },
                ],
            },
        ],
    }


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


def build_team_memory_created_card(suggestion: dict[str, Any]) -> dict[str, Any]:
    memory_id = str(suggestion.get("memory_id") or "")
    content = suggestion.get("content") or ""
    risk_level = str((suggestion.get("metadata") or {}).get("risk_level") or "normal")
    next_review = suggestion.get("due_at") or "待计算"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "已创建团队知识遗忘曲线"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**{content}**\n\n"
                    f"风险等级：{risk_level}\n"
                    f"下次复习：{next_review}\n\n"
                    "系统将按遗忘曲线定期提醒复习。"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "知道了"},
                        "type": "primary",
                        "value": {
                            "source": "larkmemory",
                            "action": "acknowledge",
                            "memory_id": memory_id,
                        },
                    },
                ],
            },
        ],
    }


def build_candidate_confirmation_card(suggestion: dict[str, Any]) -> dict[str, Any]:
    memory_id = str(suggestion.get("memory_id") or "")
    content = suggestion.get("content") or ""
    risk_level = str((suggestion.get("metadata") or {}).get("risk_level") or "normal")
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "yellow",
            "title": {"tag": "plain_text", "content": "是否为此知识创建复习提醒？"},
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"**{content}**\n\n"
                    f"风险等级：{risk_level}\n"
                    "系统检测到一条可能值得长期保留的团队知识。\n"
                    "是否创建遗忘曲线并定期提醒复习？"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "确认创建"},
                        "type": "primary",
                        "value": {
                            "source": "larkmemory",
                            "action": "promote_to_active",
                            "memory_id": memory_id,
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "忽略"},
                        "value": {
                            "source": "larkmemory",
                            "action": "dismiss_candidate",
                            "memory_id": memory_id,
                        },
                    },
                ],
            },
        ],
    }
