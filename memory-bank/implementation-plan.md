# 实施计划

## 阶段 1：梳理现有基础 ✅ 已完成

目标：确认当前 schema、storage、retrieval、plugin mock 链路的完成度。

任务：

- 阅读 `src/schemas/`，确认 `NormalizedEvent`、`MemoryCore` 等核心模型。
- 阅读 `src/storage/` 和对应测试，确认 event store、memory core store、embedding store 能力。
- 阅读 `src/retrieval/` 和对应测试，确认 intent、rewrite、fusion、rerank、trace 当前能力。
- 阅读 `plugin/`，确认 OpenClaw 插件 mock 调用链。

验收：

- 列出已有能力、缺口和下一步代码任务。
- 不修改未授权模块。

## 阶段 2：实现最小记忆闭环 ✅ 已完成

目标：跑通事件写入、记忆生成、存储、检索的最小闭环。

- 标准化 ingest 输入。
- 将事件转换为 `MemoryCore`。
- 写入 event store 和 memory core store。
- 支持基础条件检索。
- 增加对应单元测试。

## 阶段 3：实现项目决策记忆 demo ✅ 已完成

目标：围绕方向 B 项目决策与上下文记忆，形成可演示 demo。

- `src/domains/project_decision/`：models / extractor / handler / retriever / ranker / versioning。
- 支持 topic、project、stage、time 等维度检索。
- 支持历史决策卡片格式输出。

## 阶段 4：实现矛盾更新与生命周期 ✅ 已完成

目标：支持冲突决策的时序覆盖。

- supersede / update 规则已实现（`core/supersede.py`、各 domain versioning）。
- 旧记忆标记为 superseded，检索默认返回 active 版本。
- 覆盖要求项目/团队/工作区维度一致。

## 阶段 5：团队知识断层与遗忘预警（方向 D）✅ 已完成

目标：实现团队关键事实、风险、提醒和复习机制。

- `src/domains/team_retention/`：models / extractor / handler / retriever / ranker / review_planner / versioning / preprocessor / llm_extractor / admission / embedding / lifecycle。
- `src/storage/team_retention_store.py`：SQLite 持久化团队保留记忆和复习计划。
- 支持向量混合召回（Chroma + embedding provider + scope 过滤）。
- 支持复习提醒（review schedule + Ebbinghaus 遗忘曲线）。
- LLM 抽取 + 后端准入复核，prompt 不暴露内部 ID。
- 敏感信息脱敏策略。

## 阶段 6：CLI 工作流记忆（方向 A）✅ 已完成

目标：让记忆引擎帮开发者记住"哪个项目、什么场景、用哪些命令参数"。

详见 progress.md 2026-05-03 条目。分为两个阶段：
- 阶段 1：后端 domain 记忆引擎（`src/domains/cli_workflow/`）。
- 阶段 2：CLI 终端客户端工具（`src/sources/cli/`）。

## 阶段 7：飞书 Source Adapter ✅ 已完成

- `src/sources/feishu/`：client（config/sdk/listener）、events（models/normalizer/dispatcher）、proactive（cards/notifier/callbacks）。
- 真实飞书 WebSocket 消息监听和卡片交互。

## 阶段 8：Embedding 与 Rerank 服务接入 ✅ 已完成

- Embedding：OpenAI-compatible API provider + 本地 SentenceTransformers provider。
- Rerank：HTTP rerank 服务接入。
- API 端点：`/api/v1/embeddings`、`/api/v1/embeddings/batch`、`/api/v1/rerank`。

## 阶段 9：服务启动配置 ✅ 已完成

- `larkmemory.env` + `larkmemory.env.example`。
- 配置文件自动加载，支持环境变量覆盖。

## 阶段 10：Core 层动态路由 ✅ 已完成

目标：统一两套路由逻辑（`Router.route_event()` 和 `IntentAnalyzer.analyze()`），消除关键词不同步问题。

- 新增 `src/core/domain_classifier.py` — 统一四域分类器：
  - LLM `atext()` 四标签纯文本（temperature=0, max_tokens=16）
  - 硬规则：`command_finished`/`command_failed` → `cli_workflow`（0ms）
  - 统一关键词降级（4 域 × ~20 词，合并自 Router + IntentAnalyzer）
  - `classify()` async / `classify_sync()` sync 双入口
- Router 和 IntentAnalyzer 各自委托 `DomainClassifier`，移除自有 LLM/关键词逻辑（共 -280 行）。
- 移除 `Router.route_query()` 死代码。
- `service.py` 创建单一 `DomainClassifier` 实例，注入 Router 和 IntentAnalyzer。

## 阶段 11：Benchmark 评测 🔜 待开始

目标：支撑自证评测报告。

任务：
- 抗干扰测试：关键记忆 + 大量无关事件 + 精准召回。
- 矛盾更新测试：冲突输入 + 时序覆盖。
- 效能指标验证：记录使用前后字符数、步骤数或查找时间。

## 阶段 12：个人偏好记忆（方向 C）🔜 待开始

目标：实现用户习惯、偏好和默认配置的隐式学习。

- `src/domains/personal_preference/`：models 已定义，extractor / handler / retriever 待实现。
