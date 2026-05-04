from __future__ import annotations

from src.schemas import EventContext, NormalizedEvent
from src.utils.time import utc_now_iso


def doc_section_to_event(
    section_content: str,
    heading: str | None,
    doc_token: str,
    doc_title: str | None,
    section_index: int,
) -> NormalizedEvent:
    """单个文档章节（已切分）→NormalizedEvent。"""
    title = heading or doc_title or f"章节 {section_index + 1}"

    return NormalizedEvent(
        event_id=f"feishu:doc:{doc_token}:{section_index}",
        event_type="doc_section",  # type: ignore[arg-type]
        source_type="feishu_doc",  # type: ignore[arg-type]
        occurred_at=utc_now_iso(),
        context=EventContext(scope="project"),
        title=title,
        content_text=section_content,
        payload={
            "doc_token": doc_token,
            "doc_title": doc_title,
            "heading": heading,
            "section_index": section_index,
        },
        tags=["doc", "section", "feishu"],
    )
