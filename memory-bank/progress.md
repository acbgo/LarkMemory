# 进度记录

## 已完成

- 明确项目定位：飞书 AI 比赛 OpenClaw 赛道参赛项目，课题为“企业级长程协作 Memory 系统”。
- 明确技术路线：OpenClaw TypeScript 插件 + 本地 Python Memory Engine。
- 插件调用链已通过 mock 输出 log 的方式跑通。
- 已实现 Python Memory Engine 的 `src/app/` 基础层：
  - `config.py`
  - `logging.py`
  - `dependencies.py`
  - `main.py`
- 已新增 `requirements.txt`，包含当前最小依赖 `fastapi`、`uvicorn`、`pytest`。
- 已新增 `tests/unit/app/`，覆盖配置解析、日志中间件、依赖缓存、FastAPI app factory 和内置 `/health`。
- 已实现 Python Memory Engine 的 `src/api/` 基础层：
  - `health.py`
  - `ingest.py`
  - `retrieve.py`
  - `update.py`
  - `proactive.py`
  - `benchmark.py`
- 已新增 API schema：
  - `src/schemas/ingest.py`
  - `src/schemas/retrieve.py`
  - `src/schemas/update.py`
  - `src/schemas/proactive.py`
  - `src/schemas/benchmark.py`
- 已新增 `tests/unit/api/`，覆盖 health、ingest、retrieve、update、proactive、benchmark。
- 已实现 Python Memory Engine 的 `src/utils/` 基础工具层：
  - `ids.py`
  - `time.py`
  - `text.py`
  - `jsonlog.py`
- 已新增 `tests/unit/utils/`，覆盖 ID、UTC 时间、文本清洗和 JSON 日志工具。
- 已实现 Python Memory Engine 的 `src/core/` 基础编排层：
  - `router.py`
  - `memory_core.py`
  - `admission_control.py`
  - `dedup_merge.py`
  - `supersede.py`
  - `decay.py`
  - `access_tracker.py`
  - `scheduler.py`
  - `service.py`
- 已新增 `tests/unit/core/`，覆盖路由、生命周期、准入、去重合并、覆盖、衰减、访问记录、调度和统一服务。
- 仓库已有基础 Python 模块：
  - `src/schemas/`
  - `src/storage/`
  - `src/retrieval/`
  - `src/llm/`
- 仓库已有对应单元测试目录。
- 已按指定结构建立 `AGENTS.md` 和 `memory-bank/` 长期上下文文档。

## 进行中

- 拆解 Python Memory Engine 的实现任务。
- 明确记忆系统的 domain、存储、检索和生命周期治理边界。
- 将白皮书、Demo 和自证评测报告的要求映射到代码实现计划。
- 准备将 API 层逐步迁移到 `MemoryService`，或进入第一个 demo domain 的实现阶段。
- 后续 app/API 层可逐步迁移到 `src/utils/` 的 ID、时间、文本和 JSON 日志工具，但当前阶段未强制重构既有模块。

## 下一步建议

1. 基于已完成的 core 层，将 API 的 ingest/retrieve/update/proactive 逐步迁移为调用 `MemoryService`。
2. 定义第一阶段最小记忆闭环：
   - ingest 一个 `NormalizedEvent`
   - 生成或写入 `MemoryCore`
   - 可按条件 retrieve
   - 有测试覆盖
3. 选择第一个 demo domain，建议优先用 `project_decision` 打通比赛演示。
4. 为第一个 demo domain 增加最小 schema、store 和 retrieval 测试。
5. 设计矛盾更新的 supersede 测试，证明旧记忆失效、新记忆生效。
6. 设计抗干扰 benchmark，证明大量无关事件后仍能召回关键记忆。
7. 设计本地 API 边界，再连接插件 mock 链路。

## 风险与注意事项

- 记忆系统容易过早复杂化，应保持小步可验证。
- 公共 schema 变更影响面大，必须同步测试。
- domain 逻辑不要侵入统一 MemoryCore 生命周期治理。
- 检索排序需要避免把不同 domain 混成一个不可解释的大排序。
- 暂不接真实飞书 API，避免过早被外部集成复杂度牵引。
- 比赛最终需要交付白皮书、Demo 和评测报告，代码实现要能支撑叙事和数据证明。

## 最近验证

- `pytest tests/unit/app -q`：22 passed。
- `pytest tests/unit/api -q`：18 passed。
- `pytest tests/unit/utils -q`：27 passed。
- `pytest tests/unit/core -q`：33 passed。
- `pytest tests/unit/app tests/unit/api -q`：41 passed。
- `pytest -q`：127 passed, 1 skipped。
- `python -m compileall src tests`：通过。
