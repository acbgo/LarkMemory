/**
 * LarkMemory OpenClaw Plugin (Demo)
 *
 * 核心流程：
 *   1. before_agent_reply → 收集飞书上下文 → mock 后端搜索记忆 → 注入上下文
 *   2. agent_end          → 异步调用 mock 后端更新记忆
 *
 * 当前为 Demo 阶段，所有后端调用均为 mock，通过 log 展示完整过程。
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

// ============================================================
// 日志工具
// ============================================================

function log(tag: string, message: string, data?: unknown) {
  const ts = new Date().toISOString();
  const prefix = `\x1b[36m[LarkMemory]\x1b[0m [${tag}]`;
  if (data !== undefined) {
    console.log(`${prefix} ${message}`);
    console.log(`\x1b[90m${JSON.stringify(data, null, 2)}\x1b[0m`);
  } else {
    console.log(`${prefix} ${message}`);
  }
}

function sep(title: string) {
  console.log(`\x1b[33m${"═".repeat(60)}\x1b[0m`);
  console.log(`\x1b[33m  ${title}\x1b[0m`);
  console.log(`\x1b[33m${"═".repeat(60)}\x1b[0m`);
}

// ============================================================
// Mock: 飞书 CLI 收集上下文
// ============================================================

async function mockCollectFeishuContext(event: unknown) {
  log("FEISHU_CLI", "模拟调用飞书 CLI 收集上下文...");

  const evt = event as Record<string, unknown>;
  const context = {
    chatId: evt.chatId ?? evt.chat_id ?? "unknown",
    userId: evt.userId ?? evt.user_id ?? "unknown",
    messageType: evt.messageType ?? evt.message_type ?? "text",
    rawEventKeys: Object.keys(evt),
  };

  log("FEISHU_CLI", "CLI 返回上下文:", context);
  return context;
}

// ============================================================
// Mock: 后端记忆搜索 API
// ============================================================

async function mockSearchMemoryApi(query: string, context: unknown) {
  log("API", `POST /api/v1/memories/search`, { query, context });

  const memories = [
    {
      id: "mem_001",
      content: "用户偏好使用表格视图展示数据",
      category: "preference",
      confidence: 0.9,
    },
    {
      id: "mem_002",
      content: "团队决定使用方案B，理由是性能提升30%",
      category: "decision",
      confidence: 1.0,
    },
  ];

  log("API", `后端返回 ${memories.length} 条记忆`, memories);
  return memories;
}

// ============================================================
// Mock: 后端记忆更新 API
// ============================================================

async function mockUpdateMemoryApi(reply: string, context: unknown) {
  log("API", `POST /api/v1/memories/update`, {
    reply: reply.substring(0, 200),
    context,
  });

  const result = {
    status: "ok",
    memoryId: `mem_${Date.now()}`,
    storedAt: new Date().toISOString(),
  };

  log("API", "后端存储成功", result);
  return result;
}

// ============================================================
// Plugin Entry
// ============================================================

export default definePluginEntry({
  id: "larkmemory-plugin",
  name: "LarkMemory Plugin",
  description: "飞书企业级长程协作 Memory 系统（Demo）",

  register(api) {
    // ----------------------------------------------------------
    // Hook 1: before_agent_reply
    // 收集上下文 → 搜索记忆 → 注入上下文
    // ----------------------------------------------------------
    api.on("before_agent_reply", async (event, ctx) => {
      sep("HOOK: before_agent_reply → 记忆搜索");

      const evt = event as Record<string, unknown>;

      // 从 cleanedBody 字段提取用户消息（根据日志确认的实际结构）
      const userMessage = typeof evt.cleanedBody === "string" ? evt.cleanedBody : "";
      log("INPUT", `用户消息: "${userMessage}"`);

      // Step 1: 通过飞书 CLI 收集上下文
      const context = await mockCollectFeishuContext(event);

      // Step 2: 调用后端搜索记忆
      const memories = await mockSearchMemoryApi(userMessage, context);

      // Step 3: 注入记忆到上下文（Demo 阶段仅打印）
      log("INJECT", `将 ${memories.length} 条记忆注入 Agent 上下文 (mock)`);

      sep("记忆搜索完成，Agent 开始回复");
      console.log();

      return { block: false };
    });

    // ----------------------------------------------------------
    // Hook 2: agent_end
    // 异步调用后端更新记忆
    // ----------------------------------------------------------
    api.on("agent_end", async (event, ctx) => {
      sep("HOOK: agent_end → 记忆更新");

      const evt = event as Record<string, unknown>;
      const reply =
        typeof evt.reply === "string"
          ? evt.reply
          : typeof evt.response === "string"
          ? evt.response
          : JSON.stringify(evt);

      log("INPUT", `Agent 回复: ${reply.substring(0, 150)}...`);

      mockUpdateMemoryApi(reply, ctx).catch((err) => {
        log("ERROR", "记忆更新失败", err);
      });

      sep("记忆更新完成（异步）");
      console.log();
    });

    log("INIT", "LarkMemory Plugin 已注册");
    log("INIT", "已注册 hooks: before_agent_reply, agent_end");
  },
});
