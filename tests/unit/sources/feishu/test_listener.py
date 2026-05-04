from __future__ import annotations

from types import SimpleNamespace

from src.sources.feishu.client.config import FeishuSettings
from src.sources.feishu.client.listener import _message_event_from_lark, build_event_handler


class _FakeBuiltHandler:
    def __init__(self, token: str, encrypt_key: str) -> None:
        self.token = token
        self.encrypt_key = encrypt_key
        self.message_handler = None
        self.card_handler = None
        self.calendar_handler = None

    def register_p2_im_message_receive_v1(self, handler):
        self.message_handler = handler
        return self

    def register_p2_card_action_trigger(self, handler):
        self.card_handler = handler
        return self

    def register_p2_calendar_event_changed_v4(self, handler):
        self.calendar_handler = handler
        return self

    def build(self):
        return self


class _FakeEventDispatcherHandler:
    @staticmethod
    def builder(token: str, encrypt_key: str) -> _FakeBuiltHandler:
        return _FakeBuiltHandler(token, encrypt_key)


class _FakeLark:
    EventDispatcherHandler = _FakeEventDispatcherHandler


class _DummyService:
    def ingest_event(self, event):
        return event

    def update_memory(self, action, **kwargs):
        return SimpleNamespace(updated=True, message="ok")


def test_build_event_handler_uses_settings_token_and_encrypt_key(monkeypatch) -> None:
    """事件处理器应使用配置中的 verification_token 和 encrypt_key。"""
    monkeypatch.setattr("src.sources.feishu.client.listener._import_lark", lambda: _FakeLark())

    settings = FeishuSettings(
        app_id="app-id",
        app_secret="app-secret",
        verification_token="verify-token",
        encrypt_key="encrypt-key",
    )

    handler = build_event_handler(memory_service=_DummyService(), settings=settings)

    assert handler.token == "verify-token"
    assert handler.encrypt_key == "encrypt-key"
    assert handler.message_handler is not None
    assert handler.card_handler is not None
    assert handler.calendar_handler is not None


def test_message_event_from_lark_extracts_required_fields() -> None:
    """消息回调对象应被正确转换为内部事件结构。"""
    payload = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                message_id="om_1",
                chat_id="oc_1",
                chat_type="group",
                message_type="text",
                content='{"text":"hello"}',
                create_time="1777132800000",
            ),
            sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_1")),
        )
    )

    event = _message_event_from_lark(payload)

    assert event is not None
    assert event.message_id == "om_1"
    assert event.chat_id == "oc_1"
    assert event.sender_id == "ou_1"
    assert event.content_text == "hello"


def test_main_passes_settings_to_event_handler(monkeypatch) -> None:
    """main 启动 WebSocket 时应把 settings 传给 event handler，避免 token/key 为空。"""
    monkeypatch.setattr("src.sources.feishu.client.listener._import_lark", lambda: _FakeLark())
    settings = FeishuSettings(
        app_id="app-id",
        app_secret="app-secret",
        verification_token="verify-token",
        encrypt_key="encrypt-key",
        enable_ws=True,
    )
    captured = {}

    class _FakeWsClient:
        def start(self):
            captured["started"] = True

    def fake_build_ws_client(input_settings, handler):
        captured["settings"] = input_settings
        captured["handler"] = handler
        return _FakeWsClient()

    monkeypatch.setattr("src.sources.feishu.client.listener.load_feishu_settings", lambda: settings)
    monkeypatch.setattr("src.sources.feishu.client.listener.get_memory_service", lambda: _DummyService())
    monkeypatch.setattr("src.sources.feishu.client.listener.build_ws_client", fake_build_ws_client)

    from src.sources.feishu.client.listener import main

    main()

    assert captured["started"] is True
    assert captured["handler"].token == "verify-token"
    assert captured["handler"].encrypt_key == "encrypt-key"
