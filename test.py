import logging
import lark_oapi as lark

from src.sources.feishu.client.config import load_feishu_settings
from src.sources.feishu.client.sdk import build_ws_client
from src.sources.feishu.client.listener import build_event_handler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


class PrintOnlyMemoryService:
    def ingest_event(self, event):
        print("\n========== NORMALIZED FEISHU EVENT ==========")
        print("event_id:", event.event_id)
        print("event_type:", event.event_type)
        print("source_type:", event.source_type)
        print("occurred_at:", event.occurred_at)
        print("user_id:", event.context.user_id)
        print("team_id/chat_id:", event.context.team_id)
        print("thread_id/message_id:", event.context.thread_id)
        print("scope:", event.context.scope)
        print("content_text:", event.content_text)
        print("payload:", event.payload)
        print("tags:", event.tags)
        print("============================================\n")

        class Result:
            event_id = event.event_id
            stored = False
            memory_ids = []
            candidate_count = 0
            message = "print only"

        return Result()

    def update_memory(self, action, **kwargs):
        print("\n========== FEISHU CARD ACTION ==========")
        print("action:", action)
        print("kwargs:", kwargs)
        print("========================================\n")

        class Result:
            updated = True
            message = "print only"

        return Result()


settings = load_feishu_settings()
handler = build_event_handler(memory_service=PrintOnlyMemoryService())
client = build_ws_client(settings, handler)

print("Starting Feishu WebSocket listener with project listener code...")
client.start()