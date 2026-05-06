function asRecord(value) {
  return value && typeof value === "object" ? value : {};
}

function textFromContentBlocks(content) {
  const parts = [];
  for (const block of content) {
    const record = asRecord(block);
    if (record.type === "text" && typeof record.text === "string" && record.text.trim()) {
      parts.push(record.text.trim());
    }
  }
  return parts.join("\n").trim();
}

function textFromMessageContent(content) {
  if (typeof content === "string") {
    return content.trim();
  }
  if (Array.isArray(content)) {
    return textFromContentBlocks(content);
  }
  return "";
}

function latestMessageText(event, roles) {
  const evt = asRecord(event);
  const messages = Array.isArray(evt.messages) ? evt.messages : [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = asRecord(messages[index]);
    const role = String(message.role ?? "");
    if (!roles.includes(role) && !(roles.includes("") && !role)) {
      continue;
    }
    const text = textFromMessageContent(message.content);
    if (text) {
      return text;
    }
  }
  return "";
}

export function extractUserQueryFromEvent(event) {
  const fromMessages = latestMessageText(event, ["user", ""]);
  if (fromMessages) {
    return extractRetrieveQuery(fromMessages);
  }

  const evt = asRecord(event);
  const candidates = [
    evt.cleanedBody,
    evt.content,
    evt.text,
    evt.message,
    evt.prompt,
    evt.input,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return extractRetrieveQuery(candidate.trim());
    }
  }
  return "";
}

export function extractAssistantReplyFromEvent(event) {
  const fromMessages = latestMessageText(event, ["assistant"]);
  if (fromMessages) {
    return fromMessages;
  }

  const evt = asRecord(event);
  for (const key of ["reply", "response", "content", "text", "message"]) {
    const value = evt[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  try {
    return JSON.stringify(evt);
  } catch {
    return String(evt);
  }
}

export function extractRetrieveQuery(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return "";
  }

  for (const marker of [
    "根据检索到的记忆告诉我：",
    "根据检索到的记忆回答：",
    "请根据检索到的记忆回答：",
  ]) {
    const index = normalized.lastIndexOf(marker);
    if (index >= 0) {
      const extracted = normalized.slice(index + marker.length).trim();
      if (extracted) {
        return extracted;
      }
    }
  }

  const withoutEnvelope = stripOpenClawEnvelope(normalized);
  const lastLine = withoutEnvelope
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .at(-1);
  return lastLine || withoutEnvelope;
}

function stripOpenClawEnvelope(text) {
  if (!looksLikeOpenClawEnvelope(text)) {
    return text;
  }

  const afterLastFence = text.replace(/^[\s\S]*```[\w-]*\s*[\s\S]*?```\s*/m, "").trim();
  if (afterLastFence && afterLastFence !== text) {
    return afterLastFence;
  }

  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const contentLines = lines.filter((line) => {
    return !(
      line.startsWith("System: [") ||
      line.endsWith("(untrusted metadata):") ||
      line.startsWith("```") ||
      line.startsWith("{") ||
      line.startsWith("}") ||
      /^"[^"]+":/.test(line)
    );
  });
  return contentLines.at(-1) || text;
}

function looksLikeOpenClawEnvelope(text) {
  return (
    text.startsWith("System: [") ||
    text.includes("Conversation info (untrusted metadata):") ||
    text.includes("Sender (untrusted metadata):")
  );
}
