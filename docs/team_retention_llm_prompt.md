# TeamRetention LLM Prompt 与准入算法方案

## 1. 设计目标

方向 D 的团队记忆链路需要把 LLM 从“裁判”改成“抽取员”：

- LLM 负责读懂事件、抽取事实、给出证据、标记不确定性和更新意图。
- 后端负责计算分数、决定 `reject` / `candidate` / `active`、判断版本覆盖、创建复习计划。

这样可以避免 LLM 自评分不可校准的问题，也便于后续用 benchmark 调整阈值。

## 2. 参考思路

参考 mem0 prompt 的公开设计思路：

- Custom Instructions 用来收窄抽取范围，避免普通闲聊进入长期记忆。
- Few-shot examples 应包含正例和负例，帮助模型学会“应该抽取什么”和“应该跳过什么”。
- 输出必须是严格 JSON，便于后端解析、测试和审计。
- 更新类 prompt 可以让 LLM 提供更新意图和证据，但最终 ADD / UPDATE / DELETE 这类写入动作应由后端生命周期策略裁决。

参考来源：

- https://docs.mem0.ai/open-source/features/custom-instructions
- https://docs.mem0.ai/open-source/features/custom-update-memory-prompt

## 3. ID 与敏感信息策略

### 3.1 不向 LLM 传真实内部 ID

不建议把真实 `event_id`、`team_id`、`project_id`、`workspace_id`、`thread_id` 直接传给 LLM。

原因：

- LLM 不需要真实 ID 才能理解事实。
- ID 会增加噪声，模型可能误把 ID 当成业务实体。
- ID 属于系统内部标识，应由后端用于 scope 隔离、权限、版本治理和入库。

传给 LLM 的上下文使用低敏语义 hint：

```json
{
  "source_type": "feishu_chat",
  "event_type": "chat_message",
  "has_team_scope": true,
  "has_project_scope": true,
  "has_workspace_scope": false,
  "sender_role_hint": "ordinary_member"
}
```

真实 ID 仍留在后端，用于：

- 生成 `version_group`。
- 限制 team / project / workspace scope。
- 判断 source authority。
- 写入 `memory_core` 和 domain store。

### 3.2 敏感信息不在 prompt 中强制脱敏

敏感信息是否传给 LLM 不由 prompt 决定，而由后端 `sensitive_policy` 决定。

建议策略：

```text
raw:
  原文进入 LLM 和 store。适用于本地模型、私有模型、权限边界明确的环境。

mask_for_llm:
  store 保留原文，LLM prompt 使用脱敏文本。适用于第三方云模型。

mask_all:
  store 和 LLM prompt 都使用脱敏文本。适用于更严格的安全场景。
```

prompt 只要求模型遵守输入：

- 如果后端传入原文，LLM 不应自行删除关键事实。
- 如果后端传入 `[REDACTED]`，LLM 应保留 `[REDACTED]`，不要编造原始值。

## 4. 算法流程

### Step 1：事件预处理

输入：`NormalizedEvent`

处理：

1. 收集可用于语义抽取的文本：`title`、`content_text`、payload 中白名单字段。
2. 根据 `sensitive_policy` 决定传给 LLM 的文本是原文还是脱敏文本。
3. 提取弱规则特征 `rule_features`。

`rule_features` 是弱提示，不是真相。它可能为空、可能不完整，也可能有误。

特征包括：

- `explicit_memory_keywords`：长期记住、请团队记住、后续统一、团队注意。
- `risk_keywords`：API key、token、合规、客户要求、截止、事故、风险、安全。
- `future_keywords`：以后、后续、下次、必须、禁止、统一按。
- `uncertainty_markers`：可能、应该、感觉、好像、待确认、回头确认。
- `update_markers`：现在、改为、更新为、不再、旧版、替换、废弃、deprecated、no longer。
- `entity_hints`：客户、项目、负责人等实体线索。
- `owner_hint`：负责人线索。

规则特征使用原则：

```text
text 原文优先级最高。
rule_features 只能辅助 LLM 注意信号。
rule_features 为空不代表没有团队记忆。
rule_features 命中关键词也不代表一定存在团队记忆。
如果 rule_features 与 text 冲突，以 text 为准。
```

### Step 2：LLM 语义抽取

LLM 只回答这些问题：

- 这条事件是否可能包含团队长期记忆？
- 稳定事实是什么？
- 事实属于哪类？
- 主要实体是什么？
- 证据文本是什么？
- 表达是否明确？
- 是否长期稳定？
- 是否会影响后续行动？
- 是否像在更新、冲突或强化旧事实？
- 是否需要人工确认？
- 判断理由是什么？

LLM 不做这些事情：

- 不输出最终分数。
- 不决定 `active`、`candidate`、`reject`。
- 不决定是否创建复习计划。
- 不决定是否真正覆盖旧记忆。

### Step 3：后端准入评分

后端根据 LLM 输出、规则特征、scope、source authority 计算分数。

推荐评分：

```text
基础候选:
+0.25 if is_team_retention_candidate

确定性:
+0.20 if certainty == explicit
+0.08 if certainty == inferred
-0.20 if certainty == speculative

长期性:
+0.15 if stability == stable
-0.15 if stability == temporary

行动影响:
+0.15 if actionability == actionable
+0.05 if actionability == informational

风险:
+0.20 if risk_level_hint == high
+0.10 if risk_level_hint == medium
+0.03 if risk_level_hint == low

显式记忆意图:
+0.15 if explicit_memory_keywords is not empty

scope:
+0.10 if team/project/workspace scope exists

不确定性:
-0.20 if uncertainty_markers is not empty
-0.20 if needs_confirmation

来源可信:
+0.20 if source_authority in owner/formal_doc/admin/confirmed
+0.05 if source_authority == ordinary_member
-0.10 if source_authority == hearsay
```

硬规则：

```text
if not is_team_retention_candidate -> reject
if no team/project/workspace scope -> candidate at most
if certainty == speculative -> candidate at most
if needs_confirmation -> candidate at most
if high risk and source_authority is low -> candidate at most
```

默认阈值：

```text
candidate_threshold = 0.45
active_threshold = 0.78
```

### Step 4：按 fact_type 应用准入 profile

不同事实类型使用不同阈值和硬约束：

```json
{
  "api_key": {
    "candidate_threshold": 0.40,
    "active_threshold": 0.85,
    "requires_authority_for_active": true,
    "high_risk_candidate_by_default": true
  },
  "compliance": {
    "candidate_threshold": 0.40,
    "active_threshold": 0.75,
    "requires_authority_for_active": true
  },
  "customer_preference": {
    "candidate_threshold": 0.45,
    "active_threshold": 0.75,
    "requires_entity_for_active": true
  },
  "deadline": {
    "candidate_threshold": 0.40,
    "active_threshold": 0.72,
    "requires_date_for_active": true
  },
  "competitor_update": {
    "candidate_threshold": 0.45,
    "active_threshold": 0.82
  },
  "team_fact": {
    "candidate_threshold": 0.45,
    "active_threshold": 0.78
  }
}
```

### Step 5：生命周期治理

对 `candidate` 或 `active` 记忆执行生命周期判断：

1. 查关系库：same scope + same entity + same fact_type + same version_group。
2. 查向量库：语义相似团队记忆候选。
3. 判断动作：

```text
same fact:
  reinforce existing

changed fact + update_intent == supersede + explicit update signal + admission active:
  supersede old

changed fact + update signal + admission candidate:
  conflict candidate, keep old active

changed fact + no update signal:
  conflict candidate

no similar memory:
  new
```

覆盖旧 active 必须谨慎：

```text
只有 admission_status == active 且存在明确更新信号时，才自动 supersede。
如果新事实只是 candidate，即使有更新信号，也不应停用旧 active。
```

### Step 6：入库与提醒

```text
reject:
- 只保留 event。
- 不写长期记忆。
- 不写 embedding。
- 不提醒。

candidate:
- 写 memory_core。
- 写 team_retention_store。
- 写 embedding。
- 不创建 review_schedule。
- 检索时带 needs_confirmation。

active:
- 写 memory_core。
- 写 team_retention_store。
- 写 embedding。
- 创建 review_schedule。
- 可主动提醒。
```

### Step 7：检索注入

检索可以召回 `active + candidate`，但注入时必须分区：

```text
[已确认团队记忆]
- active memories

[待确认团队记忆]
- candidate memories
- 不得作为确定事实直接引用
```

## 5. 中文 LLM Prompt

### System Prompt

```text
你是一个企业协作场景下的团队长期记忆抽取器。

你的任务是从标准化协作事件中抽取“可能值得团队长期记住”的事实。

请严格遵守：
1. 你只负责语义抽取和解释，不负责最终决定是否入库。
2. 你不能输出最终分数。
3. 你不能决定 active、candidate 或 reject。
4. 你不能决定是否创建复习计划。
5. 你不能决定是否真正覆盖旧记忆。
6. 不要编造事件中没有的信息。
7. 如果信息是猜测、传闻、表达含糊或缺少来源，请标记为需要确认。
8. 如果输入中包含 [REDACTED]，请保留 [REDACTED]，不要尝试还原。
9. 如果输入中包含原始敏感信息，不要自行删除关键事实；是否脱敏由后端策略决定。
10. 只返回 JSON，不要输出 Markdown、解释文字或额外字段。
```

### User Prompt Template

```json
{
  "context_hints": {
    "source_type": "{{source_type}}",
    "event_type": "{{event_type}}",
    "has_team_scope": "{{has_team_scope}}",
    "has_project_scope": "{{has_project_scope}}",
    "has_workspace_scope": "{{has_workspace_scope}}",
    "sender_role_hint": "{{sender_role_hint}}"
  },
  "text": "{{llm_input_text}}",
  "rule_features": {
    "description": "后端规则提取的弱提示，可能为空、不完整或有误。请优先根据 text 原文判断；如果 rule_features 与 text 冲突，以 text 为准。",
    "explicit_memory_keywords": "{{explicit_memory_keywords}}",
    "risk_keywords": "{{risk_keywords}}",
    "future_keywords": "{{future_keywords}}",
    "uncertainty_markers": "{{uncertainty_markers}}",
    "update_markers": "{{update_markers}}",
    "entity_hints": "{{entity_hints}}",
    "owner_hint": "{{owner_hint}}"
  },
  "task": "请抽取可能的团队长期记忆。不要打分，不要决定最终状态。",
  "allowed_values": {
    "fact_type": [
      "api_key",
      "customer_preference",
      "competitor_update",
      "compliance",
      "deadline",
      "risk",
      "team_fact"
    ],
    "certainty": ["explicit", "inferred", "speculative"],
    "stability": ["stable", "temporary", "unknown"],
    "actionability": ["actionable", "informational", "unclear"],
    "risk_level_hint": ["low", "medium", "high"],
    "update_intent": ["none", "reinforce", "conflict", "supersede"]
  },
  "output_schema": {
    "is_team_retention_candidate": "boolean",
    "fact_type": "string",
    "fact_value": "string",
    "summary": "string",
    "primary_entity": {
      "type": "string",
      "name": "string",
      "normalized_key": "string"
    },
    "owner_hint": "string|null",
    "risk_level_hint": "low|medium|high",
    "validity": {
      "valid_from": "string|null",
      "valid_to": "string|null",
      "is_temporary": "boolean"
    },
    "certainty": "explicit|inferred|speculative",
    "stability": "stable|temporary|unknown",
    "actionability": "actionable|informational|unclear",
    "update_intent": "none|reinforce|conflict|supersede",
    "update_signal_text": "string|null",
    "needs_confirmation": "boolean",
    "confirmation_reason": "string|null",
    "evidence_text": "string",
    "reason": "string"
  }
}
```

### One-shot 正例

```json
{
  "example_input": {
    "context_hints": {
      "source_type": "feishu_chat",
      "event_type": "chat_message",
      "has_team_scope": true,
      "has_project_scope": true,
      "has_workspace_scope": false,
      "sender_role_hint": "ordinary_member"
    },
    "text": "请团队长期记住：客户 A 后续导出必须使用 xlsx，不接受 csv。",
    "rule_features": {
      "description": "后端规则提取的弱提示，可能为空、不完整或有误。请优先根据 text 原文判断；如果 rule_features 与 text 冲突，以 text 为准。",
      "explicit_memory_keywords": ["长期记住"],
      "risk_keywords": ["客户"],
      "future_keywords": ["后续", "必须"],
      "uncertainty_markers": [],
      "update_markers": [],
      "entity_hints": ["客户 A"],
      "owner_hint": null
    }
  },
  "example_output": {
    "is_team_retention_candidate": true,
    "fact_type": "customer_preference",
    "fact_value": "客户 A 要求导出文件使用 xlsx，不接受 csv。",
    "summary": "客户 A 导出格式要求：使用 xlsx，不接受 csv。",
    "primary_entity": {
      "type": "customer",
      "name": "客户 A",
      "normalized_key": "customer-a"
    },
    "owner_hint": null,
    "risk_level_hint": "medium",
    "validity": {
      "valid_from": null,
      "valid_to": null,
      "is_temporary": false
    },
    "certainty": "explicit",
    "stability": "stable",
    "actionability": "actionable",
    "update_intent": "none",
    "update_signal_text": null,
    "needs_confirmation": false,
    "confirmation_reason": null,
    "evidence_text": "客户 A 后续导出必须使用 xlsx，不接受 csv",
    "reason": "这是客户交付约束，会影响团队后续处理导出文件。"
  }
}
```

### One-shot 负例

```json
{
  "example_input": {
    "context_hints": {
      "source_type": "feishu_chat",
      "event_type": "chat_message",
      "has_team_scope": true,
      "has_project_scope": true,
      "has_workspace_scope": false,
      "sender_role_hint": "ordinary_member"
    },
    "text": "收到，我下午看一下。",
    "rule_features": {
      "description": "后端规则提取的弱提示，可能为空、不完整或有误。请优先根据 text 原文判断；如果 rule_features 与 text 冲突，以 text 为准。",
      "explicit_memory_keywords": [],
      "risk_keywords": [],
      "future_keywords": [],
      "uncertainty_markers": [],
      "update_markers": [],
      "entity_hints": [],
      "owner_hint": null
    }
  },
  "example_output": {
    "is_team_retention_candidate": false,
    "fact_type": "team_fact",
    "fact_value": "",
    "summary": "",
    "primary_entity": {
      "type": "",
      "name": "",
      "normalized_key": ""
    },
    "owner_hint": null,
    "risk_level_hint": "low",
    "validity": {
      "valid_from": null,
      "valid_to": null,
      "is_temporary": true
    },
    "certainty": "speculative",
    "stability": "temporary",
    "actionability": "unclear",
    "update_intent": "none",
    "update_signal_text": null,
    "needs_confirmation": false,
    "confirmation_reason": null,
    "evidence_text": "",
    "reason": "这是普通协作回复，没有稳定团队事实。"
  }
}
```

### One-shot 规则特征为空但仍应抽取

```json
{
  "example_input": {
    "context_hints": {
      "source_type": "feishu_chat",
      "event_type": "chat_message",
      "has_team_scope": true,
      "has_project_scope": true,
      "has_workspace_scope": false,
      "sender_role_hint": "ordinary_member"
    },
    "text": "A 那边导出还是老规矩，别给 csv。",
    "rule_features": {
      "description": "后端规则提取的弱提示，可能为空、不完整或有误。请优先根据 text 原文判断；如果 rule_features 与 text 冲突，以 text 为准。",
      "explicit_memory_keywords": [],
      "risk_keywords": [],
      "future_keywords": [],
      "uncertainty_markers": [],
      "update_markers": [],
      "entity_hints": [],
      "owner_hint": null
    }
  },
  "example_output": {
    "is_team_retention_candidate": true,
    "fact_type": "customer_preference",
    "fact_value": "客户 A 不接受 csv 导出。",
    "summary": "客户 A 导出要求：不要提供 csv。",
    "primary_entity": {
      "type": "customer",
      "name": "客户 A",
      "normalized_key": "customer-a"
    },
    "owner_hint": null,
    "risk_level_hint": "medium",
    "validity": {
      "valid_from": null,
      "valid_to": null,
      "is_temporary": false
    },
    "certainty": "inferred",
    "stability": "stable",
    "actionability": "actionable",
    "update_intent": "none",
    "update_signal_text": null,
    "needs_confirmation": true,
    "confirmation_reason": "原文使用了'A 那边'和'老规矩'，客户实体和规则来自上下文推断，需要确认。",
    "evidence_text": "A 那边导出还是老规矩，别给 csv。",
    "reason": "这可能是客户导出格式约束，会影响团队后续交付，但表达依赖上下文。"
  }
}
```

