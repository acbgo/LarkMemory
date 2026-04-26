/**
 * LarkMemory OpenClaw Plugin
 *
 * Hook 流程：
 *   before_agent_reply → 搜索相关记忆，注入到上下文
 *   agent_end          → 从对话中提取新记忆，调用 API 存储
 *
 * 当前为 Demo 阶段，所有操作均为 mock，通过 log 展示完整过程。
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { Type } from "@sinclair/typebox";

// ============================================================
// Mock Memory Store（Demo 阶段的本地内存存储）
// ============================================================

interface MemoryItem {
  id: string;
  content: string;
  category: "preference" | "decision" | "fact" | "behavior";
  source: "explicit" | "implicit";
  confidence: number;
  createdAt: string;
}

let memoryIdCounter = 1;

const mockMemoryStore: MemoryItem[] = [
  {
    id: "mem_001",
    content: "用户偏好使用表格视图展示数据",
    category: "preference",
    source: "implicit",
    confidence: 0.9,
    createdAt: "2026-04-20T10:00:00Z",
  },
  {
    id: "mem_002",
    content: "团队决定使用方案B而非方案A，理由是性能提升30%",
    category: "decision",
    source: "explicit",
    confidence: 1.0,
    createdAt: "2026-04-22T14:30:00Z",
  },
  {
    id: "mem_003",
    content: "用户每周五下午3点整理周报",
    category: "behavior",
    source: "implicit",
    confidence: 0.85,
    createdAt: "2026-04-23T15:00:00Z",
  },
  {
    id: "mem_004",
    content: "API密钥已更新为sk-xxx，旧密钥已失效",
    category: "fact",
    source: "explicit",
    confidence: 1.0,
    createdAt: "2026-04-24T09:00:00Z",
  },
];

// ============================================================
// Mock Memory API
// ============================================================

function mockSearchMemory(query: string): MemoryItem[] {
  const keywords = query.toLowerCase().split(/\s+/);
  return mockMemoryStore
    .map((item) => {
      const text = item.content.toLowerCase();
      const matchCount = keywords.filter((kw) => text.includes(kw)).length;
      const score = matchCount / keywords.length;
      return { item, score };
    })
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((r) => r.item);
}

function mockAddMemory(
  content: string,
  category: MemoryItem["category"] = "fact"
): MemoryItem {
  const newItem: MemoryItem = {
    id: `mem_${String(memoryIdCounter++).padStart(3, "0")}`,
    content,
    category,
    source: "explicit",
    confidence: 0.7,
    createdAt: new Date().toISOString(),
  };
  mockMemoryStore.push(newItem);
  return newItem;
}

// ============================================================
// 简易关键词提取（Demo 用，生产环境替换为 LLM 提取）
// ============================================================

function extractKeywords(text: string): string[] {
  const stopWords = new Set([
    "的",
    "了",
    "是",
    "在",
    "我",
    "你",
    "他",
    "她",
    "它",
    "们",
    "这",
    "那",
    "和",
    "与",
    "或",
    "不",
    "有",
    "没",
    "会",
    "能",
    "要",
    "把",
    "被",
    "给",
    "对",
    "从",
    "到",
    "上",
    "下",
    "中",
    "里",
    "吗",
    "呢",
    "吧",
    "啊",
    "哦",
    "嗯",
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "can",
    "shall",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "as",
    "into",
    "about",
    "it",
    "i",
    "me",
    "my",
    "we",
    "our",
    "you",
    "your",
    "he",
    "she",
    "they",
    "them",
    "what",
    "which",
    "who",
    "that",
    "this",
    "and",
    "but",
    "if",
    "or",
    "not",
    "no",
  ]);

  return text
    .split(/[\s,，。.！!？?；;：:、\n]+/)
    .filter((w) => w.length > 1 && !stopWords.has(w.toLowerCase()));
}

// ============================================================
// 日志工具
// ============================================================

function pluginLog(tag: string, message: string, data?: unknown) {
  const timestamp = new Date().toISOString();
  const prefix = `\x1b[36m[LarkMemory]\x1b[0m [${timestamp}] [${tag}]`;
  if (data !== undefined) {
    console.log(`${prefix} ${message}`);
    console.log(
      `\x1b[90m${JSON.stringify(data, null, 2)}\x1b[0m`
    );
  } else {
    console.log(`${prefix} ${message}`);
  }
}

function separator(title: string) {
  console.log(
    `\x1b[33m${"═".repeat(60)}\x1b[0m`
  );
  console.log(`\x1b[33m  ${title}\x1b[0m`);
  console.log(
    `\x1b[33m${"═".repeat(60)}\x1b[0m`
  );
}

// ============================================================
// Plugin Entry
// ============================================================

export default definePluginEntry({
  id: "larkmemory-plugin",
  name: "LarkMemory Plugin",
  description:
    "Memory 系统插件",

  register(api) {
    // ----------------------------------------------------------
    // Hook 1: before_agent_reply
    // 在 Agent 回复前，搜索与用户输入相关的记忆
    // ----------------------------------------------------------
    api.on(
      "before_agent_reply",
      async (event, ctx) => {
        separator("HOOK: before_agent_reply → 记忆搜索");

        // 从 event 中获取用户消息内容
        const userMessage =
          (event as Record<string, unknown>)?.userMessage ??
          (event as Record<string, unknown>)?.message ??
          (event as Record<string, unknown>)?.content ??
          "";

        const query =
          typeof userMessage === "string"
            ? userMessage
            : JSON.stringify(userMessage);

        pluginLog("INPUT", `用户消息: ${query}`);

        // Step 1: 提取关键词
        const keywords = extractKeywords(query);
        pluginLog("EXTRACT", `提取关键词: [${keywords.join(", ")}]`);

        // Step 2: 搜索记忆
        const searchQuery = keywords.join(" ");
        pluginLog("SEARCH", `搜索记忆: "${searchQuery}"`);

        const results = mockSearchMemory(searchQuery);

        // Step 3: 展示搜索结果
        if (results.length > 0) {
          pluginLog("HIT", `命中 ${results.length} 条相关记忆:`, results);
        } else {
          pluginLog("MISS", "未命中相关记忆");
        }

        // Step 4: 模拟注入记忆到上下文
        pluginLog(
          "INJECT",
          `将 ${results.length} 条记忆注入 Agent 上下文 (mock)`
        );

        separator("记忆搜索完成，Agent 开始回复");
        console.log();

        // 不阻塞，允许 Agent 正常回复
        return { block: false };
      },
      { priority: 50 }
    );

    // ----------------------------------------------------------
    // Hook 2: agent_end
    // 在 Agent 回复完成后，提取新记忆并存储
    // ----------------------------------------------------------
    api.on(
      "agent_end",
      async (event, ctx) => {
        separator("HOOK: agent_end → 记忆存储");

        // 从 event 中获取对话内容
        const eventData = event as Record<string, unknown>;
        const agentReply =
          eventData?.reply ??
          eventData?.response ??
          eventData?.content ??
          "";
        const replyText =
          typeof agentReply === "string"
            ? agentReply
            : JSON.stringify(agentReply);

        pluginLog("INPUT", `Agent 回复: ${replyText.substring(0, 200)}...`);

        // Step 1: 判断是否值得记忆（简单规则）
        const shouldRemember =
          replyText.length > 20 &&
          (replyText.includes("决定") ||
            replyText.includes("确认") ||
            replyText.includes("偏好") ||
            replyText.includes("以后") ||
            replyText.includes("更新") ||
            replyText.includes("记住") ||
            replyText.includes("重要") ||
            replyText.includes("截止") ||
            replyText.includes("密钥"));

        if (!shouldRemember) {
          pluginLog("SKIP", "回复内容不包含高价值记忆信号，跳过存储");
          separator("记忆存储完成（跳过）");
          console.log();
          return;
        }

        // Step 2: 提取记忆内容
        pluginLog("EXTRACT", "检测到高价值信息，开始提取记忆...");

        // Mock: 根据关键词判断记忆类别
        let category: MemoryItem["category"] = "fact";
        if (
          replyText.includes("决定") ||
          replyText.includes("确认") ||
          replyText.includes("选择")
        ) {
          category = "decision";
        } else if (
          replyText.includes("偏好") ||
          replyText.includes("喜欢") ||
          replyText.includes("习惯")
        ) {
          category = "preference";
        } else if (
          replyText.includes("每周") ||
          replyText.includes("定时") ||
          replyText.includes("规律")
        ) {
          category = "behavior";
        }

        // Step 3: 调用 Memory API 存储（mock）
        const memoryContent = replyText.substring(0, 200);
        pluginLog("STORE", `存储记忆 [${category}]: "${memoryContent}"`);

        const newMemory = mockAddMemory(memoryContent, category);

        pluginLog("RESULT", `记忆已存储:`, {
          id: newMemory.id,
          category: newMemory.category,
          confidence: newMemory.confidence,
          createdAt: newMemory.createdAt,
        });

        // Step 4: 展示当前记忆库状态
        pluginLog(
          "STATS",
          `记忆库总计: ${mockMemoryStore.length} 条记忆`,
          {
            preference: mockMemoryStore.filter(
              (m) => m.category === "preference"
            ).length,
            decision: mockMemoryStore.filter(
              (m) => m.category === "decision"
            ).length,
            fact: mockMemoryStore.filter((m) => m.category === "fact").length,
            behavior: mockMemoryStore.filter(
              (m) => m.category === "behavior"
            ).length,
          }
        );

        separator("记忆存储完成");
        console.log();
      },
      { priority: 50 }
    );

    // ----------------------------------------------------------
    // 注册 memory_search 工具（供 Agent 主动调用）
    // ----------------------------------------------------------
    api.registerTool({
      name: "memory_search",
      description:
        "搜索 LarkMemory 记忆系统中的相关记忆。可用于查找用户偏好、团队决策、历史事实等。",
      parameters: Type.Object({
        query: Type.String({
          description: "搜索查询，描述你想查找的记忆内容",
        }),
        category: Type.Optional(
          Type.Enum(
            {
              preference: "preference",
              decision: "decision",
              fact: "fact",
              behavior: "behavior",
            },
            { description: "记忆类别过滤（可选）" }
          )
        ),
        limit: Type.Optional(
          Type.Number({
            description: "返回结果数量上限",
            default: 5,
          })
        ),
      }),
      async execute(_id, params) {
        separator("TOOL: memory_search");

        pluginLog("TOOL_CALL", `Agent 调用 memory_search`, params);

        let results = mockSearchMemory(params.query);

        if (params.category) {
          results = results.filter(
            (m) => m.category === params.category
          );
        }

        const limit = params.limit ?? 5;
        results = results.slice(0, limit);

        pluginLog("TOOL_RESULT", `返回 ${results.length} 条记忆`);

        return {
          content: [
            {
              type: "text" as const,
              text:
                results.length > 0
                  ? JSON.stringify(
                      results.map((m) => ({
                        id: m.id,
                        content: m.content,
                        category: m.category,
                        confidence: m.confidence,
                        createdAt: m.createdAt,
                      })),
                      null,
                      2
                    )
                  : "未找到相关记忆",
            },
          ],
        };
      },
    });

    // ----------------------------------------------------------
    // 注册 memory_store 工具（供 Agent 主动调用）
    // ----------------------------------------------------------
    api.registerTool({
      name: "memory_store",
      description:
        "向 LarkMemory 记忆系统存储一条新记忆。适用于保存重要决策、用户偏好、关键事实等。",
      parameters: Type.Object({
        content: Type.String({
          description: "要存储的记忆内容",
        }),
        category: Type.Enum(
          {
            preference: "preference",
            decision: "decision",
            fact: "fact",
            behavior: "behavior",
          },
          { description: "记忆类别" }
        ),
      }),
      async execute(_id, params) {
        separator("TOOL: memory_store");

        pluginLog("TOOL_CALL", `Agent 调用 memory_store`, params);

        const newMemory = mockAddMemory(params.content, params.category);

        pluginLog("TOOL_RESULT", `记忆已存储: ${newMemory.id}`);

        return {
          content: [
            {
              type: "text" as const,
              text: JSON.stringify(
                {
                  status: "stored",
                  memory: {
                    id: newMemory.id,
                    content: newMemory.content,
                    category: newMemory.category,
                    confidence: newMemory.confidence,
                  },
                },
                null,
                2
              ),
            },
          ],
        };
      },
    });

    pluginLog("INIT", "LarkMemory Plugin 已注册");
    pluginLog("INIT", "已注册 hooks: before_agent_reply, agent_end");
    pluginLog("INIT", "已注册 tools: memory_search, memory_store");
    pluginLog(
      "INIT",
      `Mock 记忆库: ${mockMemoryStore.length} 条初始记忆`
    );
  },
});
