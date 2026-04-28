"""Tests for the standalone Feishu chat list demo script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[4] / "lark-oapi-demo" / "chat_list_demo.py"
SPEC = importlib.util.spec_from_file_location("lark_oapi_demo_chat_list_demo", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
CHAT_LIST_DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHAT_LIST_DEMO)


def test_build_chat_list_params_clamps_page_size() -> None:
    """会话列表参数应限制 page_size，并在有 page_token 时附带翻页游标。"""
    params = CHAT_LIST_DEMO._build_chat_list_params(999, "next-page")

    assert params == {
        "page_size": "100",
        "page_token": "next-page",
    }


def test_collect_all_chats_paginates_until_has_more_is_false() -> None:
    """会话列表收集器应持续翻页，直到接口不再返回 has_more。"""
    seen_params: list[dict[str, str]] = []

    def fake_fetch_page(_: str, params: dict[str, str]) -> dict[str, object]:
        seen_params.append(params)
        if len(seen_params) == 1:
            return {
                "items": [{"chat_id": "oc_1"}],
                "has_more": True,
                "page_token": "page-2",
            }
        return {
            "items": [{"chat_id": "oc_2"}],
            "has_more": False,
            "page_token": "",
        }

    payload = CHAT_LIST_DEMO._collect_all_chats("token", page_size=20, fetch_page=fake_fetch_page)

    assert [params.get("page_token") for params in seen_params] == [None, "page-2"]
    assert payload["total"] == 2
    assert payload["pages_fetched"] == 2
    assert [item["chat_id"] for item in payload["items"]] == ["oc_1", "oc_2"]


def test_fetch_chat_list_can_attach_recent_messages(monkeypatch) -> None:
    """当启用 include_messages 时，每个会话都应补充最近消息。"""
    monkeypatch.setattr(CHAT_LIST_DEMO, "_resolve_access_token", lambda *_args: ("user-token", "user"))
    monkeypatch.setattr(
        CHAT_LIST_DEMO,
        "_collect_all_chats",
        lambda *_args, **_kwargs: {
            "total": 2,
            "pages_fetched": 1,
            "items": [
                {"chat_id": "oc_group", "name": "项目群", "chat_type": "group"},
                {"chat_id": "oc_p2p", "name": "张三", "chat_type": "p2p"},
            ],
        },
    )
    monkeypatch.setattr(
        CHAT_LIST_DEMO,
        "_list_recent_messages",
        lambda _token, chat_id, limit: [{"message_id": f"om_{chat_id}", "limit": limit}],
    )

    payload = CHAT_LIST_DEMO.fetch_chat_list(
        "app-id",
        "app-secret",
        include_messages=True,
        messages_per_chat=2,
    )

    assert payload["total"] == 2
    assert payload["auth_mode"] == "user"
    assert payload["include_messages"] is True
    assert payload["messages_per_chat"] == 2
    assert payload["items"][0]["recent_messages"][0]["message_id"] == "om_oc_group"
    assert payload["items"][1]["last_message_preview"]["message_id"] == "om_oc_p2p"


def test_require_args_accepts_user_access_token_without_app_credentials() -> None:
    """只提供 user_access_token 时，参数校验也应通过。"""
    args = CHAT_LIST_DEMO.argparse.Namespace(
        user_access_token="u-demo",
        app_id="",
        app_secret="",
    )

    CHAT_LIST_DEMO._require_args(args)


def test_resolve_access_token_prefers_user_access_token(monkeypatch) -> None:
    """当调用方显式提供 user_access_token 时，不应再回退到 tenant token。"""
    called: dict[str, bool] = {"tenant": False}

    def fake_fetch_tenant_access_token(_app_id: str, _app_secret: str) -> str:
        called["tenant"] = True
        return "tenant-token"

    monkeypatch.setattr(CHAT_LIST_DEMO, "_fetch_tenant_access_token", fake_fetch_tenant_access_token)

    token, auth_mode = CHAT_LIST_DEMO._resolve_access_token("u-demo", "app-id", "app-secret")

    assert token == "u-demo"
    assert auth_mode == "user"
    assert called["tenant"] is False
