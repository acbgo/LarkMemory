import assert from "node:assert/strict";
import test from "node:test";

import {
  extractAssistantReplyFromEvent,
  extractRetrieveQuery,
  extractUserQueryFromEvent,
} from "./text_extraction.mjs";

const wrappedFeishuQuery = `System: [2026-05-06 14:29:44 UTC] Feishu[default] DM | ou_db4e8f8c303122824b022d4d2e29514e [msg:om_x100b50814bb564b4b3fe06a16939533]

Conversation info (untrusted metadata):
\`\`\`json
{
  "message_id": "om_x100b50814bb564b4b3fe06a16939533",
  "sender_id": "ou_db4e8f8c303122824b022d4d2e29514e",
  "sender": "ou_db4e8f8c303122824b022d4d2e29514e",
  "timestamp": "Wed 2026-05-06 14:29 UTC"
}
\`\`\`

Sender (untrusted metadata):
\`\`\`json
{
  "label": "ou_db4e8f8c303122824b022d4d2e29514e",
  "id": "ou_db4e8f8c303122824b022d4d2e29514e",
  "name": "ou_db4e8f8c303122824b022d4d2e29514e"
}
\`\`\`

多路召回之后用什么方法做融合？`;

test("extractRetrieveQuery removes OpenClaw Feishu metadata envelope", () => {
  assert.equal(extractRetrieveQuery(wrappedFeishuQuery), "多路召回之后用什么方法做融合？");
});

test("extractUserQueryFromEvent prefers current direct content over stale message history", () => {
  const event = {
    content: wrappedFeishuQuery,
    messages: [
      { role: "system", content: "system prompt" },
      { role: "user", content: "上一轮用户问题是什么？" },
    ],
  };

  assert.equal(extractUserQueryFromEvent(event), "多路召回之后用什么方法做融合？");
});

test("extractAssistantReplyFromEvent prefers latest assistant message", () => {
  const event = {
    content: JSON.stringify({ messages: [{ role: "assistant", content: "不要把整段 JSON 当回复" }] }),
    messages: [
      { role: "user", content: "问题" },
      { role: "assistant", content: [{ type: "text", text: "这是助手回复" }] },
    ],
  };

  assert.equal(extractAssistantReplyFromEvent(event), "这是助手回复");
});
