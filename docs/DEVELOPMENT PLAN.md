# OpenClaw记忆引擎插件基本模块开发目录说明

本文档对openClaw记忆引擎插件下每个主要文件的职责做说明，便于快速理解项目结构。

## 总览

`src/` 里的文件大致分成几类：

- 存储层：负责记忆的持久化、迁移、压缩
- 提取层：负责从对话中抽取记忆、分类、去重、补 metadata
- 检索层：负责召回、排序、融合、降噪、可观测性
- 生命周期层：负责衰减、tier、访问强化
- 会话与反思层：负责 session memory、reflection、恢复
- 治理与边界层：负责 scope、workspace 边界、准入控制
- 工具层：负责给 Agent 和 CLI 暴露能力

---

## 核心主链路文件

### `store.ts`

底层存储核心。封装 LanceDB 的表初始化、增删改查、向量搜索、BM25/FTS 搜索、统计以及写锁控制。

### `embedder.ts`

向量化核心。统一 embedding provider，处理维度、缓存、chunking、任务类型和错误提示。

### `retriever.ts`

检索核心。把向量搜索、BM25、融合、rerank、长度归一化、时间衰减、噪声过滤和多样性控制整合成完整检索流水线。

### `smart-extractor.ts`

记忆自动提取核心。把对话内容转成结构化记忆，负责 LLM 抽取、去重、合并、跳过、support、supersede 等决策。

### `smart-metadata.ts`

记忆元数据核心。定义一条记忆的语义结构、source/state/layer/tier、关系链和多层摘要。

---

## 存储与数据维护

### `migrate.ts`

迁移入口。负责旧数据迁移到当前插件格式。

### `memory-upgrader.ts`

旧记忆升级器。把 legacy memory 升级为带 smart metadata 的新格式。

### `memory-compactor.ts`

记忆压缩器。扫描旧且相似的记忆，聚类后合成一条更干净的新记忆，减少冗余碎片。

### `batch-dedup.ts`

批量近重复检测。用于在提取结果进入主流程前，先做候选记忆内部去重。

### `chunker.ts`

长文本切块。给 embedding 或长上下文处理做分块。

---

## 记忆分类与时间语义

### `memory-categories.ts`

智能分类定义。定义 `profile/preferences/entities/events/cases/patterns` 等语义分类，以及哪些类型偏向 merge/supersede。

### `temporal-classifier.ts`

时间语义判断。识别静态/动态记忆，推断过期时间，支持 temporal fact。

### `preference-slots.ts`

偏好槽位抽象。把某些偏好标准化成更适合 merge/update 的结构。

### `identity-addressing.ts`

身份与称呼处理。帮助处理“我/你/他”等 addressing 场景下的抽取和规范化。

---

## 检索增强与可观测性

### `query-expander.ts`

查询扩展。给 BM25 增加同义词、标签等高信号补充。

### `intent-analyzer.ts`

意图分析。为 adaptive recall 判断当前 query 更偏向哪类记忆、需要多深的召回。

### `adaptive-retrieval.ts`

检索门控。判断短消息、寒暄、低价值输入是否应跳过 auto-recall。

### `retrieval-trace.ts`

检索追踪。记录每个阶段的候选和裁剪过程，便于调试。

### `retrieval-stats.ts`

检索统计。收集检索质量和阶段性统计信息。

### `access-tracker.ts`

访问强化。记录某条记忆被命中/使用的次数和时间，给衰减与排序提供依据。

---

## 生命周期与层级管理

### `decay-engine.ts`

遗忘/衰减模型。根据 recency、frequency、importance、confidence 计算生命周期得分。

### `tier-manager.ts`

tier 晋升/降级管理。控制 `core / working / peripheral` 的演化。

### `admission-control.ts`

准入控制。在写入前拦截不该入库或低价值的候选记忆。

### `admission-stats.ts`

准入统计。对 admission control 的拒绝和原因做聚合统计。

---

## 噪声处理

### `noise-filter.ts`

噪声识别。基于规则判断哪些文本是无价值噪声，例如系统包裹元数据、低信息内容。

### `noise-prototypes.ts`

噪声原型库。通过 embedding 累积噪声样本，提升语言无关的噪声过滤能力。

### `auto-capture-cleanup.ts`

自动捕获文本清洗。对 `agent_end` 自动抓取的消息做清洗，去除系统注入和反思提示等无关内容。

---

## 会话压缩、恢复与反思

### `session-compressor.ts`

会话压缩。对当前对话做价值评估和裁剪，保留高信息片段再送入提取流程。

### `session-recovery.ts`

session 恢复。处理 `/new`、reset、session 文件定位和历史恢复相关逻辑。

### `reflection-store.ts`

反思写库。把 session reflection 结果写入 LanceDB，并支持 reflection slices 的读取。

### `reflection-slices.ts`

反思切片提取。从 reflection 结果中抽出可注入和可治理的片段。

### `reflection-retry.ts`

反思重试。给 reflection 过程提供一次性容错和瞬时重试机制。

### `reflection-ranking.ts`

反思排序。决定哪些 reflection 项更值得保留或注入。

### `reflection-metadata.ts`

反思元数据定义。管理 reflection 相关展示标签和字段。

### `reflection-mapped-metadata.ts`

反思映射元数据。把 reflection 内容映射成普通记忆 metadata。

### `reflection-item-store.ts`

反思条目存储。管理单条 reflection item。

### `reflection-event-store.ts`

反思事件存储。管理一次 reflection 事件及其 ID 和事件级元数据。

---

## 作用域、边界与团队协作

### `scopes.ts`

scope 隔离核心。定义 `global / agent:* / project:* / user:* / reflection:*` 等作用域及访问控制。

### `clawteam-scope.ts`

团队 scope 扩展。给现有 scope 管理器动态补充团队共享 scope。

### `workspace-boundary.ts`

工作区边界。处理 USER.md 专属记忆与 LanceDB 记忆的边界，避免混淆和污染。

---

## LLM 与提示词

### `llm-client.ts`

LLM 客户端封装。供 smart extraction、reflection 等模块统一调用模型。

### `llm-oauth.ts`

OAuth 登录支持。对应 `memory-pro auth login/status/logout` 等命令。

### `extraction-prompts.ts`

抽取提示词模板。定义提取、去重、合并时使用的 prompt。

---

## 工具与辅助文件

### `tools.ts`

Agent 工具层。注册 `memory_store / memory_recall / memory_update / memory_forget / memory_stats / memory_list` 等工具。

### `self-improvement-files.ts`

自改进文件管理。处理 self-improvement 的日志和学习文件。

## 项目基础模块构建规划

##### 阶段一：统一记忆模型、raw数据层管理、episode提取（结构化事件）

##### 阶段二：konwledge固化（长期项目理解），多层检索引擎（L1,L2,L3），决策卡片(事件决策的定义，项目state)

##### 阶段三：偏好记忆、规则/提醒、遗忘曲线与版本覆盖

##### 阶段四：日报周报、决策时间线、真实飞书数据接入、demo

## 总结

这个项目不是一个单一的“记忆表封装”，而是一整套围绕记忆的工程体系：

- 写入前有清洗、提取、分类、去重
- 存储中有 metadata、scope、版本兼容
- 检索时有融合、rerank、降噪、解释
- 后台还有衰减、压缩、反思、治理

如果后续还要继续深入，建议下一步按“运行链路”而不是按文件名继续读代码。
