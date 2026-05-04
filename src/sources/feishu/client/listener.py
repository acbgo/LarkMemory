from __future__ import annotations

import json
import logging
from typing import Any

from src.app.dependencies import get_memory_service
from src.sources.feishu.events.calendar_models import FeishuCalendarEvent
from src.sources.feishu.events.calendar_normalizer import calendar_event_to_normalized_event
from src.sources.feishu.events.dispatcher import FeishuEventDispatcher
from src.sources.feishu.events.doc_models import FeishuDocChangedEvent
from src.sources.feishu.events.doc_processor import DocProcessor
from src.sources.feishu.events.meeting_models import FeishuMeetingEndedEvent
from src.sources.feishu.events.meeting_normalizer import meeting_ended_to_event
from src.sources.feishu.events.meeting_processor import MeetingProcessor
from src.sources.feishu.events.models import FeishuMessageEvent
from src.sources.feishu.events.normalizer import extract_text_from_message_content
from src.sources.feishu.events.task_models import FeishuTaskEvent
from src.sources.feishu.events.task_normalizer import task_event_to_normalized_event
from src.sources.feishu.proactive.callbacks import FeishuCardActionHandler, parse_card_action
from src.storage.source_state_store import SourceStateStore

from .config import load_feishu_settings
from .sdk import build_ws_client, _import_lark


logger = logging.getLogger(__name__)


def build_event_handler(
    memory_service: Any | None = None,
    settings: Any | None = None,
    source_state_store: SourceStateStore | None = None,
    vc_client: Any | None = None,
    doc_client: Any | None = None,
) -> Any:
    """Build lark-oapi event handler for Feishu messages, card actions, and multi-source events."""
    lark = _import_lark()
    service = memory_service or get_memory_service()
    dispatcher = FeishuEventDispatcher(service)
    card_handler = FeishuCardActionHandler(service)

    meeting_processor: MeetingProcessor | None = None
    if source_state_store is not None and vc_client is not None:
        meeting_processor = MeetingProcessor(source_state_store, vc_client, dispatcher)

    doc_processor: DocProcessor | None = None
    if source_state_store is not None and doc_client is not None:
        doc_processor = DocProcessor(source_state_store, doc_client, dispatcher)

    def on_message(data: Any) -> None:
        message_event = _message_event_from_lark(data)
        if message_event is None:
            logger.info("function=src.sources.feishu.client.listener.on_message action=skip_empty")
            return
        dispatcher.dispatch_message(message_event)

    def on_calendar_event(data: Any) -> None:
        cal_event = _calendar_event_from_lark(data)
        if cal_event is None:
            logger.info("function=src.sources.feishu.client.listener.on_calendar_event action=skip_empty")
            return
        normalized = calendar_event_to_normalized_event(cal_event)
        dispatcher.dispatch_normalized_event(normalized)

    def on_task_event(data: Any) -> None:
        task_event = _task_event_from_lark(data)
        if task_event is None:
            logger.info("function=src.sources.feishu.client.listener.on_task_event action=skip_empty")
            return
        normalized = task_event_to_normalized_event(task_event)
        dispatcher.dispatch_normalized_event(normalized)

    def on_meeting_ended(data: Any) -> None:
        meeting = _meeting_ended_from_lark(data)
        if meeting is None:
            logger.info("function=src.sources.feishu.client.listener.on_meeting_ended action=skip_empty")
            return
        normalized = meeting_ended_to_event(meeting)
        dispatcher.dispatch_normalized_event(normalized)
        if meeting_processor is not None:
            meeting_processor.process_meeting_ended_async(meeting.meeting_id, meeting.topic)

    def on_doc_changed(data: Any) -> None:
        doc = _doc_changed_from_lark(data)
        if doc is None:
            logger.info("function=src.sources.feishu.client.listener.on_doc_changed action=skip_empty")
            return
        if doc_processor is not None:
            doc_processor.process_doc_changed_async(doc.doc_token, doc.title)

    def on_card_action(data: Any) -> Any:
        raw_action = _card_action_from_lark(data)
        response_payload = card_handler.handle(parse_card_action(raw_action))
        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse  # type: ignore[import-not-found]
        except ImportError:
            return response_payload
        return P2CardActionTriggerResponse(response_payload)

    handler_builder = (
        lark.EventDispatcherHandler.builder(
            getattr(settings, "verification_token", "") if settings is not None else "",
            getattr(settings, "encrypt_key", "") if settings is not None else "",
        )
        .register_p2_im_message_receive_v1(on_message)
        .register_p2_card_action_trigger(on_card_action)
        .register_p2_calendar_event_changed_v4(on_calendar_event)
        .register_p2_task_updated_v2(on_task_event)
    )
    if meeting_processor is not None:
        handler_builder = handler_builder.register_p2_vc_meeting_ended_v1(on_meeting_ended)
    if doc_processor is not None:
        handler_builder = handler_builder.register_p2_doc_updated_v1(on_doc_changed)
    return handler_builder.build()


def main() -> None:
    """Start the Feishu WebSocket listener as a standalone source worker."""
    settings = load_feishu_settings()
    if not settings.enable_ws:
        raise RuntimeError("Feishu WebSocket listener is disabled; set LARKMEMORY_FEISHU_ENABLE_WS=true")
    client = build_ws_client(settings, build_event_handler(settings=settings))
    client.start()


def _message_event_from_lark(data: Any) -> FeishuMessageEvent | None:
    event = getattr(data, "event", None)
    message = getattr(event, "message", None)
    sender = getattr(event, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    message_id = getattr(message, "message_id", None)
    chat_id = getattr(message, "chat_id", None)
    message_type = getattr(message, "message_type", "text")
    if not message_id or not chat_id:
        return None
    content_text = extract_text_from_message_content(message_type, getattr(message, "content", None))
    return FeishuMessageEvent(
        message_id=str(message_id),
        chat_id=str(chat_id),
        chat_type=str(getattr(message, "chat_type", "") or ""),
        sender_id=getattr(sender_id, "open_id", None),
        message_type=str(message_type),
        content_text=content_text,
        create_time=str(getattr(message, "create_time", "") or "") or None,
        raw_payload=_safe_payload(data),
    )


def _card_action_from_lark(data: Any) -> dict[str, Any]:
    event = getattr(data, "event", None)
    action = getattr(event, "action", None)
    operator = getattr(event, "operator", None)
    return {
        "value": getattr(action, "value", {}) or {},
        "operator": {"open_id": getattr(operator, "open_id", None)},
        "raw": _safe_payload(data),
    }


def _calendar_event_from_lark(data: Any) -> FeishuCalendarEvent | None:
    event = getattr(data, "event", None)
    if event is None:
        return None
    calendar_event_id = getattr(event, "event_id", None)
    summary = getattr(event, "summary", "") or ""
    if not calendar_event_id or not summary:
        return None

    attendee_ids: list[str] = []
    raw_attendees = getattr(event, "attendees", None)
    if isinstance(raw_attendees, list):
        for a in raw_attendees:
            a_id = getattr(a, "id", None) if not isinstance(a, str) else a
            if a_id:
                attendee_ids.append(str(a_id))

    organizer_id = None
    organizer = getattr(event, "organizer", None)
    if organizer is not None:
        organizer_id = getattr(organizer, "id", None)

    return FeishuCalendarEvent(
        calendar_event_id=str(calendar_event_id),
        summary=str(summary),
        description=str(getattr(event, "description", "") or ""),
        start_time=_nested_attr_str(event, "start_time", "date_time"),
        end_time=_nested_attr_str(event, "end_time", "date_time"),
        organizer_id=organizer_id,
        attendee_ids=attendee_ids,
        location=_nested_attr_str(event, "location", "name"),
        recurrence=_attr_str(event, "recurrence"),
        status=_attr_str(event, "status") or "confirmed",
        raw_payload=_safe_payload(data),
    )


def _doc_changed_from_lark(data: Any) -> FeishuDocChangedEvent | None:
    event = getattr(data, "event", None)
    if event is None:
        return None
    doc_token = getattr(event, "doc_token", None)
    if not doc_token:
        return None
    user_id = None
    operator = getattr(event, "operator", None)
    if operator is not None:
        user_id = getattr(operator, "id", None)
    return FeishuDocChangedEvent(
        doc_token=str(doc_token),
        doc_type=_attr_str(event, "doc_type") or "docx",
        title=_attr_str(event, "title"),
        change_type=_attr_str(event, "change_type") or "",
        user_id=user_id,
        raw_payload=_safe_payload(data),
    )


def _meeting_ended_from_lark(data: Any) -> FeishuMeetingEndedEvent | None:
    event = getattr(data, "event", None)
    if event is None:
        return None
    meeting_id = getattr(event, "meeting_id", None)
    if not meeting_id:
        return None
    topic = getattr(event, "topic", "") or getattr(event, "name", "") or "未命名会议"

    participant_ids: list[str] = []
    raw_participants = getattr(event, "participants", None)
    if isinstance(raw_participants, list):
        for p in raw_participants:
            p_id = getattr(p, "id", None) if not isinstance(p, str) else p
            if p_id:
                participant_ids.append(str(p_id))

    organizer_id = None
    organizer = getattr(event, "organizer", None)
    if organizer is not None:
        organizer_id = getattr(organizer, "id", None)

    return FeishuMeetingEndedEvent(
        meeting_id=str(meeting_id),
        topic=str(topic),
        start_time=_attr_str(event, "start_time"),
        end_time=_attr_str(event, "end_time"),
        organizer_id=organizer_id,
        participant_ids=participant_ids,
        raw_payload=_safe_payload(data),
    )


def _task_event_from_lark(data: Any) -> FeishuTaskEvent | None:
    event = getattr(data, "event", None)
    if event is None:
        return None
    task_id = getattr(event, "task_id", None)
    task_name = getattr(event, "name", "") or getattr(event, "summary", "") or ""
    if not task_id or not task_name:
        return None

    assignee_ids: list[str] = []
    raw_assignees = getattr(event, "assignees", None)
    if isinstance(raw_assignees, list):
        for a in raw_assignees:
            a_id = getattr(a, "id", None) if not isinstance(a, str) else a
            if a_id:
                assignee_ids.append(str(a_id))

    follower_ids: list[str] = []
    raw_followers = getattr(event, "followers", None)
    if isinstance(raw_followers, list):
        for f in raw_followers:
            f_id = getattr(f, "id", None) if not isinstance(f, str) else f
            if f_id:
                follower_ids.append(str(f_id))

    creator_id = None
    creator = getattr(event, "creator", None)
    if creator is not None:
        creator_id = getattr(creator, "id", None)

    tasklist_name = None
    tasklist = getattr(event, "tasklist", None)
    if tasklist is not None:
        tasklist_name = getattr(tasklist, "name", None)

    return FeishuTaskEvent(
        task_id=str(task_id),
        task_name=str(task_name),
        description=str(getattr(event, "description", "") or ""),
        status=_attr_str(event, "status") or "",
        start_time=_nested_attr_str(event, "start_time", "date_time"),
        due_time=_nested_attr_str(event, "due_time", "date_time"),
        creator_id=creator_id,
        assignee_ids=assignee_ids,
        follower_ids=follower_ids,
        tasklist_name=tasklist_name,
        priority=_attr_str(event, "priority"),
        url=_attr_str(event, "url"),
        raw_payload=_safe_payload(data),
    )


def _attr_str(obj: Any, name: str) -> str | None:
    value = getattr(obj, name, None)
    if value is None:
        return None
    s = str(value)
    return s or None


def _nested_attr_str(obj: Any, outer: str, inner: str) -> str | None:
    outer_obj = getattr(obj, outer, None)
    if outer_obj is None:
        return None
    inner_val = getattr(outer_obj, inner, None)
    if inner_val is None:
        return None
    s = str(inner_val)
    return s or None


def _safe_payload(data: Any) -> dict[str, Any]:
    if hasattr(data, "raw"):
        raw = getattr(data, "raw")
        if isinstance(raw, dict):
            return raw
    try:
        return json.loads(json.dumps(data, default=lambda item: getattr(item, "__dict__", str(item))))
    except Exception:
        return {}


if __name__ == "__main__":
    main()
