"""Tests for the standalone Feishu cli demo script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[4] / "lark-oapi-demo" / "cli_demo.py"
SPEC = importlib.util.spec_from_file_location("lark_oapi_demo_cli_demo", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
CLI_DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI_DEMO)


def test_build_message_list_params_clamps_page_size_and_adds_optional_filters() -> None:
    """The message list query should respect Feishu defaults and include optional time filters."""
    params = CLI_DEMO._build_message_list_params(
        "oc_demo",
        sort="desc",
        page_size=99,
        start="2026-04-01T00:00:00+08:00",
        end="2026-04-02T00:00:00+08:00",
        page_token="next-page",
    )

    assert params == {
        "container_id_type": "chat",
        "container_id": "oc_demo",
        "sort_type": "ByCreateTimeDesc",
        "page_size": "50",
        "card_msg_content_type": "raw_card_content",
        "only_thread_root_messages": "true",
        "start_time": "2026-04-01T00:00:00+08:00",
        "end_time": "2026-04-02T00:00:00+08:00",
        "page_token": "next-page",
    }


def test_collect_all_messages_paginates_until_has_more_is_false() -> None:
    """The history collector should continue with page_token until the API reports completion."""
    seen_params: list[dict[str, str]] = []

    def fake_fetch_page(_: str, params: dict[str, str]) -> dict[str, object]:
        seen_params.append(params)
        if len(seen_params) == 1:
            return {
                "items": [{"message_id": "om_1"}],
                "has_more": True,
                "page_token": "page-2",
            }
        return {
            "items": [{"message_id": "om_2"}],
            "has_more": False,
            "page_token": "",
        }

    payload = CLI_DEMO._collect_all_messages(
        "token",
        "oc_demo",
        sort="asc",
        page_size=20,
        start=None,
        end=None,
        fetch_page=fake_fetch_page,
    )

    assert [params.get("page_token") for params in seen_params] == [None, "page-2"]
    assert payload["chat_id"] == "oc_demo"
    assert payload["total"] == 2
    assert payload["pages_fetched"] == 2
    assert [item["message_id"] for item in payload["messages"]] == ["om_1", "om_2"]


def test_fetch_user_history_prefers_chat_id_and_skips_user_resolution(monkeypatch) -> None:
    """When chat_id is given directly, the script should skip user profile and p2p chat lookup."""
    monkeypatch.setattr(CLI_DEMO, "_fetch_tenant_access_token", lambda *_args: "tenant-token")
    monkeypatch.setattr(
        CLI_DEMO,
        "_collect_all_messages",
        lambda *_args, **_kwargs: {
            "chat_id": "oc_direct",
            "total": 1,
            "pages_fetched": 1,
            "messages": [{"message_id": "om_direct"}],
        },
    )

    payload = CLI_DEMO.fetch_user_history(
        "app-id",
        "app-secret",
        chat_id="oc_direct",
        sort="asc",
        page_size=10,
    )

    assert payload["chat_id"] == "oc_direct"
    assert payload["resolved_open_id"] is None
    assert payload["messages"][0]["message_id"] == "om_direct"


def test_resolve_open_id_rejects_non_open_id_inputs() -> None:
    """The demo should fail fast when the caller passes user_id or union_id without open_id scope support."""
    try:
        CLI_DEMO._resolve_open_id("tenant-token", "5cfacac4", "user_id")
    except RuntimeError as exc:
        assert "只直接支持 open_id" in str(exc)
        assert "--chat-id" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for non-open_id inputs")
