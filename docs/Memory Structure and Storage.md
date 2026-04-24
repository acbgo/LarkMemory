# Memory 结构定义与存储方案

## 一、设计原则

这套系统不应该做成：

- 四套完全割裂的 memory 系统
- 一个没有语义区分的大杂烩 memory 桶

推荐方案是：

- `一个统一的 Memory Engine`
- `多个按场景路由的 memory domain`
- `共享的生命周期治理能力`
- `按领域区分 schema、排序策略与触发策略`

这样既能兼顾工程复用，也便于比赛答辩时形成清晰的平台叙事。

---

## 二、总体架构

```text
OpenClaw TS Plugin
-> ingest API / retrieve API
-> Python Memory Engine
-> ingest router / retrieve router
-> domain extractors / domain rankers
-> storage layer
-> scheduler / decay / version manager / access tracker
```

### 统一平台负责的内容

- 事件标准化
- scope 隔离
- 记忆准入控制
- 版本覆盖与 supersede 管理
- 遗忘与衰减
- 检索融合
- 命中统计
- benchmark 支撑

### 各 domain 负责的内容

- 领域专属抽取逻辑
- 领域专属排序逻辑
- 领域专属主动触发策略
- 领域专属 merge / overwrite 规则

---

## 三、统一核心 Memory 模型

所有记忆项共享一个统一“外壳”，作为平台治理层。

```ts
type MemoryDomain =
  | "cli_workflow"
  | "project_decision"
  | "personal_preference"
  | "team_retention";

type MemoryScope =
  | "user"
  | "project"
  | "team"
  | "workspace"
  | "global";

interface MemoryCore {
  memory_id: string;
  domain: MemoryDomain;
  memory_type: string;
  scope: MemoryScope;
  source_type: string;
  source_ref: string;
  source_event_id?: string;
  content_text: string;
  summary_text?: string;
  entities?: string[];
  tags?: string[];
  importance: number;
  confidence: number;
  freshness_score?: number;
  status: "active" | "candidate" | "superseded" | "expired" | "forgotten";
  valid_from?: string;
  valid_to?: string;
  overwrite_of?: string;
  superseded_by?: string;
  trigger_policy_id?: string;
  decay_policy_id?: string;
  embedding_id?: string;
  created_at: string;
  updated_at: string;
}
```

这个模型负责：

- 所有 memory 的统一标识
- 生命周期状态管理
- 版本覆盖关系管理
- 跨域检索融合
- 治理与统计

每个 domain 在此基础上扩展自己的结构化字段。

---

## 四、四个方向的 Domain Schema

## 1. CLI 工作流记忆

```ts
interface CliWorkflowMemory {
  memory_id: string;
  repo_id?: string;
  workspace_id?: string;
  cwd_pattern?: string;
  task_label?: string;
  command_template: string;
  arg_slots?: Record<string, string>;
  workflow_prev?: string;
  workflow_next?: string;
  success_rate?: number;
  avg_latency_ms?: number;
  last_used_at?: string;
}
```

用途：

- 记录部署、构建、排障等命令模板
- 记录 repo 级参数偏好
- 记录多步工作流中的前后步骤关系

---

## 2. 项目决策记忆

```ts
interface ProjectDecisionMemory {
  memory_id: string;
  project_id: string;
  topic: string;
  decision: string;
  rationale?: string;
  alternatives?: string[];
  opponents_or_risks?: string[];
  owner?: string;
  stage?: string;
  deadline?: string;
  decision_time?: string;
  version_group?: string;
}
```

用途：

- 记录为什么选择方案 B 而不是 A
- 追踪项目历史决策链
- 支持时序覆盖与版本切换

---

## 3. 个人偏好记忆

```ts
interface PersonalPreferenceMemory {
  memory_id: string;
  user_id: string;
  preference_key?: string;
  preferred_value?: string;
  context_pattern?: string;
  routine_pattern?: string;
  trigger_time_rule?: string;
  rule_expression?: string;
  confidence_score?: number;
  last_confirmed_at?: string;
}
```

用途：

- 记录用户偏好的默认视图与行为方式
- 支撑例行提醒与自动化触发
- 基于用户稳定习惯个性化 Agent 行为

---

## 4. 团队长期保留记忆

```ts
interface TeamRetentionMemory {
  memory_id: string;
  team_id?: string;
  project_id?: string;
  fact_type: string;
  fact_value: string;
  risk_level?: "low" | "medium" | "high";
  owner?: string;
  expiry_time?: string;
  review_cycle?: string;
  next_review_at?: string;
  version_group?: string;
  review_count?: number;
}
```

用途：

- 保存 API key 更新、客户约束、合规规则等关键事实
- 绑定复习计划与遗忘曲线
- 支撑主动预警与版本失效管理

---

## 五、推荐的存储方案

## 1. 总体思路

推荐采用：

`共享主表 + domain 子表 + 向量索引 + 原始事件表`

逻辑结构建议如下：

```text
event_store
memory_core
memory_cli_workflow
memory_project_decision
memory_personal_preference
memory_team_retention
memory_embeddings
memory_access_log
memory_review_schedule
```

这样设计的优点是：

- 有统一治理层，便于平台化表达
- 每个方向又能保留自己的结构化字段
- 检索时可以按 domain 使用不同排序逻辑
- 避免所有字段混在一张稀疏大表里
- 白皮书和答辩时容易讲清楚

---

## 2. `event_store`

保存从 OpenClaw 插件与飞书侧集成进入的原始标准化事件。

建议字段：

- `event_id`
- `event_type`
- `source_type`
- `user_id`
- `project_id`
- `team_id`
- `workspace_id`
- `payload_json`
- `occurred_at`
- `ingested_at`

作用：

- 支撑 ingest 重放
- 支撑抽取质量 benchmark
- 支撑路由与抽取调试

---

## 3. `memory_core`

保存所有 memory 共用的核心元数据。

建议字段：

- `memory_id`
- `domain`
- `memory_type`
- `scope`
- `source_type`
- `source_ref`
- `content_text`
- `summary_text`
- `importance`
- `confidence`
- `status`
- `valid_from`
- `valid_to`
- `overwrite_of`
- `superseded_by`
- `trigger_policy_id`
- `decay_policy_id`
- `created_at`
- `updated_at`

作用：

- 统一生命周期管理
- 统一过滤与治理
- 跨域检索融合

---

## 4. Domain 子表

每个 domain 单独有一张结构化子表，保存领域特有字段。

关联方式：

- 所有子表都用 `memory_id` 关联 `memory_core`

例如：

- `memory_cli_workflow`
- `memory_project_decision`
- `memory_personal_preference`
- `memory_team_retention`

作用：

- 保留各方向自己的业务结构
- 支持领域专属排序与统计
- 支持领域专属覆盖规则

---

## 5. `memory_embeddings`

保存语义检索所需的 embedding 信息。

建议字段：

- `embedding_id`
- `memory_id`
- `domain`
- `embedding_vector`
- `chunk_index`
- `model_name`
- `created_at`

作用：

- 语义召回
- 混合检索中的向量能力支撑

---

## 6. `memory_access_log`

记录每条 memory 的检索命中、使用与反馈情况。

建议字段：

- `access_id`
- `memory_id`
- `access_type`
- `query_id`
- `agent_session_id`
- `used_in_response`
- `feedback_signal`
- `accessed_at`

作用：

- 优化排序
- 强化高价值记忆
- 为衰减与保留提供依据

---

## 7. `memory_review_schedule`

记录需要复习、提醒、遗忘管理的 memory 调度信息。

建议字段：

- `schedule_id`
- `memory_id`
- `review_policy`
- `next_review_at`
- `last_review_at`
- `review_count`
- `risk_level`
- `active`

作用：

- 执行遗忘曲线策略
- 定时生成主动提醒任务

---

## 六、写入路由策略

所有进入系统的事件都应先走统一 ingest router，而不是直接写表。

```text
normalized event
-> event classifier
-> 判断属于哪个 domain
-> 调用对应 extractor
-> 生成 MemoryCore + DomainPayload
-> 执行 dedup / merge / conflict resolution
-> 写入 memory_core + domain 子表 + embedding + policy 关系
```

推荐的路由规则：

- shell / tool 执行事件 -> `cli_workflow`
- 聊天 / 文档 / 会议中的决策事件 -> `project_decision`
- 重复个人行为或显式偏好 -> `personal_preference`
- 团队关键事实或需复习事项 -> `team_retention`

---

## 七、检索路由策略

不要让所有 domain 混在一起做同一套排序。

正确做法是：

`按意图路由到目标 domain，再分别召回，最后融合`

```text
query context
-> intent analyzer
-> 选择目标 domains
-> 各 domain 独立召回
-> 各 domain 独立排序
-> cross-domain fusion
-> 将 top memories 注入 Agent 上下文
```

典型示例：

- 部署 / 运行 / 排障任务
  - 主查：`cli_workflow`
  - 可辅查：`team_retention`

- “为什么当时这么决策”
  - 主查：`project_decision`

- “按我平时习惯来”
  - 主查：`personal_preference`

- “提醒我团队之前强调过什么”
  - 主查：`team_retention`
  - 可辅查：`project_decision`

---

## 八、生命周期与更新规则

## 1. Admission Control

并不是每条事件都应该进入长期记忆。

建议策略：

- 高价值结构化事实：直接准入
- 重复模式：达到阈值后准入
- 低置信度候选：先进入 candidate 状态
- 低价值噪声：直接拒绝

---

## 2. Dedup 与 Merge

同一 domain 中，很多 memory 更适合 merge，而不是一味 insert。

示例：

- 重复出现的命令模板：更新频次与成功率
- 同一用户偏好：强化置信度
- 相同团队关键事实：更新复习次数与最近确认时间

---

## 3. Supersede 与版本覆盖

发生冲突时，不能简单地把新旧记忆并列存放而不建立关系。

示例：

- 截止日期被新的日期替换
- 旧决策被新结论推翻
- 周报接收人从 A 改成 B
- API key 或客户约束出现新版本

建议处理方式：

- 旧 memory 标记为 `superseded`
- 建立 `old_memory_id -> superseded_by` 关系
- 检索时优先返回最新有效版本

---

## 4. Forgetting 与 Decay

不同 domain 应采用不同的衰减策略，而不是统一处理。

建议：

- `cli_workflow`：按近期使用频率与成功率衰减
- `project_decision`：项目活跃期内低衰减，项目结束后归档
- `personal_preference`：用户持续忽略时降权
- `team_retention`：不做静默遗忘，而是依赖 review schedule 与显式失效

---

## 九、建议的落地优先级

如果开发时间有限，建议按以下顺序实现：

1. `memory_core + event_store`
2. `cli_workflow` 与 `project_decision` 子表
3. `team_retention` 的 review schedule
4. `personal_preference` 的模式识别逻辑
5. 跨域检索融合

这样既能保持平台架构完整，又能优先打透 1 到 2 个最强 Demo 场景。

---

## 十、适合比赛答辩的总结表述

建议对外统一表述为：

`我们设计的是一套面向 OpenClaw 的企业级长期记忆平台。平台采用统一 Memory Core 与按场景路由的 Domain Schema 设计，在不替换原有记忆引擎的前提下，实现记忆的提取、存储、检索、更新、遗忘与主动服务。`

这套方案的关键特征是：

- 旁路集成 OpenClaw
- 统一生命周期治理
- 分领域结构化建模
- 支持冲突覆盖与遗忘管理
- 支持主动提醒与上下文注入
- 能够支撑抗干扰测试、矛盾更新测试与效能 benchmark
