# 实施计划

## 阶段 1：梳理现有基础

目标：确认当前 schema、storage、retrieval、plugin mock 链路的完成度。

任务：

- 阅读 `src/schemas/`，确认 `NormalizedEvent`、`MemoryCore` 等核心模型。
- 阅读 `src/storage/` 和对应测试，确认 event store、memory core store、embedding store 能力。
- 阅读 `src/retrieval/` 和对应测试，确认 intent、rewrite、fusion、rerank、trace 当前能力。
- 阅读 `plugin/`，确认 OpenClaw 插件 mock 调用链。

验收：

- 列出已有能力、缺口和下一步代码任务。
- 不修改未授权模块。

## 阶段 2：实现最小记忆闭环

目标：跑通事件写入、记忆生成、存储、检索的最小闭环。

任务：

- 标准化 ingest 输入。
- 将事件转换为 `MemoryCore`。
- 写入 event store 和 memory core store。
- 支持基础条件检索。
- 增加对应单元测试。

验收：

- 一个测试能证明事件被写入并形成可检索记忆。
- store 行为有读、写、查、更新的基本测试。

## 阶段 3：实现项目决策记忆 demo

目标：围绕比赛方向中的项目决策与上下文记忆，形成可演示 demo。

任务：

- 定义 project decision payload。
- 实现决策记忆写入和查询。
- 支持 topic、project、stage、time 等维度检索。
- 支持历史决策卡片格式输出。
- 增加单元测试。

验收：

- 能从模拟飞书讨论事件中写入项目决策记忆。
- 后续相关 query 能召回正确决策。

## 阶段 4：实现矛盾更新与生命周期

目标：支持冲突决策的时序覆盖。

任务：

- 设计 supersede/update 规则。
- 同一 topic 出现新决策时，将旧决策标记为 superseded。
- 检索时默认返回 active 版本。
- 必要时保留历史版本链。

验收：

- 矛盾更新测试通过：先输入“周报发给 A”，再输入“周报发给 B”，系统返回 B，旧记忆不再作为当前有效结果。

## 阶段 5：设计 Benchmark

目标：支撑自证评测报告。

任务：

- 抗干扰测试：关键记忆 + 大量无关事件 + 精准召回。
- 矛盾更新测试：冲突输入 + 时序覆盖。
- 效能指标验证：记录使用前后字符数、步骤数或查找时间。

验收：

- Benchmark 可以重复运行。
- 输出能用于评测报告。

## 阶段 6：插件与 Demo 联动

目标：将 Memory Engine 与 OpenClaw 插件 mock 链路连接。

任务：

- 设计本地 API 边界。
- 插件调用 retrieve/ingest。
- 在 mock 或本地演示中展示记忆卡片注入。
- 为后续真实飞书 API 接入保留边界。

验收：

- Demo 能展示事件写入、记忆召回、主动提示或上下文注入。

