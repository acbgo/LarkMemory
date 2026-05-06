/**
 * LarkMemory OpenClaw Plugin (Demo)
 *
 * before_prompt_build: rawPrompt → retrieve → inject context
 * agent_end: ingest reply + user query
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

type PluginConfig = {
  memoryApiBase: string;
  userId: string;
  requestTimeoutMs: number;
};

type BackendMemoryHit = {
  memory_id?: string;
  domain?: string;
  content_text?: string;
  summary_text?: string | null;
  score?: number;
};

type BackendRetrieveResponse = {
  status?: string;
  results?: BackendMemoryHit[];
};

const DEFAULT_CONFIG: PluginConfig = {
  memoryApiBase: "http://127.0.0.1:8765",
  userId: "default_user",
  requestTimeoutMs: 60000,
};

const TEAM_ID = "oc_b9cef0cb9a14fe72a58793560cc4aa1c";

const LOG_FILE_URL = new URL("./larkmemory-plugin.log", import.meta.url);

function log(tag: string, message: string, data?: unknown) {
  const prefix = `[LarkMemory] [${tag}]`;
  const line = data !== undefined
    ? `${prefix} ${message}\n${JSON.stringify(data, null, 2)}`
    : `${prefix} ${message}`;
  console.log(line);
  const timestamp = new Date().toISOString();
  import("node:fs")
    .then((fs) => fs.appendFileSync(LOG_FILE_URL, `${timestamp} ${line}\n`, "utf8"))
    .catch(() => {});
}

async function postJson<T>(url: string, body: unknown, config: PluginConfig): Promise<T | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json; charset=utf-8" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    log("ERROR", `POST ${url} failed`);
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function buildMemoryContext(memories: BackendMemoryHit[]): string {
  if (memories.length === 0) return "";
  const lines = memories.map((m, i) => {
    const score = typeof m.score === "number" ? ` (score=${m.score.toFixed(3)})` : "";
    const text = (m.summary_text || m.content_text || "(empty)").slice(0, 300);
    return `${i + 1}. [${m.domain ?? "unknown"}]${score} ${text}`;
  });
  return [
    "LarkMemory retrieved relevant long-term memories:",
    ...lines,
    "Use these memories only when relevant to the current user request.",
  ].join("\n");
}

export default definePluginEntry({
  id: "larkmemory-plugin",
  name: "LarkMemory Plugin",
  description: "飞书企业级长程协作 Memory 系统",

  register(api) {
    const config = DEFAULT_CONFIG;
    const apiBase = `${config.memoryApiBase}/api/v1`;
    let lastUserQuery = "";

    api.on("before_prompt_build", async (event) => {
      const query = (event.prompt as string) ?? "";
      lastUserQuery = query;
      log("HOOK", `before_prompt_build | query="${query}"`);

      if (!query.trim()) return {};

      // Retrieve memories
      const res = await postJson<BackendRetrieveResponse>(`${apiBase}/retrieve`, {
        query_text: query,
        user_id: config.userId,
        team_id: TEAM_ID,
        top_k: 5,
      }, config);

      const memories = res?.results ?? [];
      log("RETRIEVE", `Got ${memories.length} memories`);

      return {
        prependContext: buildMemoryContext(memories),
      };
    });

    api.on("agent_end", async (event) => {
      const reply = String((event as Record<string, unknown>).reply ?? (event as Record<string, unknown>).response ?? "");
      log("HOOK", `agent_end | reply="${reply.slice(0, 100)}"`);

      if (!reply.trim() && !lastUserQuery.trim()) return;

      // Ingest conversation for memory extraction
      await postJson(`${apiBase}/ingest`, {
        event_type: "chat_message",
        source_type: "openclaw",
        occurred_at: new Date().toISOString(),
        content_text: reply,
        context: { user_id: config.userId, team_id: TEAM_ID },
        payload: { user_query: lastUserQuery, agent_reply: reply },
        tags: ["openclaw"],
      }, config);
    });

    log("INIT", "Plugin registered");
  },
});
