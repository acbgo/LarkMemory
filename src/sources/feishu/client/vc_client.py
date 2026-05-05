from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from src.sources.feishu.events.meeting_models import MeetingNotesData

logger = logging.getLogger(__name__)

_MINUTE_TOKEN_RE = re.compile(r"/minutes/([a-zA-Z0-9]+)")


class FeishuVcClientProtocol(Protocol):
    """VC API 调用协议，方便测试时 mock。"""

    def get_recording(self, meeting_id: str) -> str:
        """获取会议录制中的 minute_token（从 recording.url 解析）。"""
        ...

    def get_meeting_notes(self, minute_token: str) -> MeetingNotesData:
        """获取妙记产物：文字记录（逐字稿）。"""
        ...


class FeishuVcClient:
    """基于 lark-oapi SDK 的 VC / 妙记 API 客户端。"""

    def __init__(self, api_client: Any) -> None:
        self._client = api_client

    # ---- 录制 ----

    def get_recording(self, meeting_id: str) -> str:
        """GET /vc/v1/meetings/{meeting_id}/recording，从 recording.url 解析 minute_token。

        lark-oapi 1.5.5 的 GetMeetingRecordingRequestBuilder 仅有 build()，
        无法设置 meeting_id，使用底层 raw request 调用。
        """
        import lark_oapi as lark  # type: ignore[import-not-found]

        req = (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.GET)
            .uri(f"/open-apis/vc/v1/meetings/{meeting_id}/recording")
            .token_types({lark.AccessTokenType.TENANT})
            .build()
        )
        response = self._client.request(req)
        if not response.success():
            raise RuntimeError(
                f"Failed to get recording for meeting {meeting_id}: "
                f"code={response.code} msg={response.msg}"
            )
        body = _body_json(response)
        recording = body.get("data", {}).get("recording", {})
        if not recording:
            raise RuntimeError(f"No recording found for meeting {meeting_id}")
        url = recording.get("url", "")
        if not url:
            raise RuntimeError(f"No recording.url for meeting {meeting_id}")
        m = _MINUTE_TOKEN_RE.search(str(url))
        if not m:
            raise RuntimeError(
                f"Cannot parse minute_token from recording.url: {url}"
            )
        minute_token = m.group(1)
        logger.info("action=parsed_minute_token meeting_id=%s token=%s", meeting_id, minute_token)
        return minute_token

    # ---- 逐字稿 ----

    def get_minute_transcript(self, minute_token: str) -> str:
        """GET /minutes/v1/minutes/{minute_token}/transcript，返回逐字稿文本。

        该接口返回导出文件内容（非 JSON），直接按 UTF-8 文本读取。
        """
        import lark_oapi as lark  # type: ignore[import-not-found]

        req = (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.GET)
            .uri(f"/open-apis/minutes/v1/minutes/{minute_token}/transcript")
            .token_types({lark.AccessTokenType.TENANT})
            .build()
        )
        response = self._client.request(req)
        if not response.success():
            raise RuntimeError(
                f"Failed to get transcript for minute {minute_token}: "
                f"code={response.code} msg={response.msg}"
            )
        if response.raw and hasattr(response.raw, "content"):
            try:
                return response.raw.content.decode("utf-8")
            except UnicodeDecodeError:
                return str(response.raw.content) if response.raw.content else ""
        return ""

    # ---- 妙记产物 ----

    def get_meeting_notes(self, minute_token: str) -> MeetingNotesData:
        """获取妙记产物：逐字稿文本。

        AI 总结/待办/章节以独立文档形式存储在妙记 artifacts 列表中
        （每项包含 artifact_type + doc_token），需单独调用文档 API 读取内容。
        当前只拉取逐字稿进入记忆引擎，AI 产物作为后续增强项。
        """
        verbatim_text = self.get_minute_transcript(minute_token)
        return MeetingNotesData(
            summary="",
            todos=[],
            chapters=[],
            verbatim_text=verbatim_text,
            minute_token=minute_token,
        )


def _body_json(response: Any) -> dict[str, Any]:
    import json
    if response.raw and hasattr(response.raw, "content") and response.raw.content:
        try:
            parsed = json.loads(response.raw.content)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}
