# 技术栈

## 后端

- 语言：Python。
- 测试：pytest。
- 当前模型：dataclass schema。
- 当前存储：本地文件/JSON 存储起步。
- 主要目录：
  - `src/schemas/`
  - `src/storage/`
  - `src/retrieval/`
  - `src/llm/`
  - `tests/`

## 插件

- 语言：TypeScript。
- 平台：飞书 OpenClaw。
- 目录：`plugin/`。
- 当前状态：插件调用链已通过 mock 输出 log 的方式跑通。

## 记忆系统

核心设计采用统一 Memory Engine：

- `NormalizedEvent`：标准化外部事件。
- `MemoryCore`：所有记忆共享的核心元数据和生命周期字段。
- domain-specific memory：不同场景的结构化记忆字段，模型定义在 `domains/*/models.py`。
- storage layer：事件、核心记忆、domain memory、embedding、access log、review schedule 等存储。
- retrieval layer：意图分析、查询改写、召回、重排、融合、trace。

## 计划扩展

- 数据库或更强持久化存储。
- 向量索引和混合检索。
- 真实飞书 API 集成。
- Benchmark runner。
- OpenClaw 插件与后端 API 的完整联动。

## 工程约束

- 当前阶段以本地可运行 Demo 为优先。
- 不把云服务作为核心路径。
- 不把真实飞书 API 作为当前必需依赖。
- 公共 schema 变更必须同步测试。
- 代码实现要服务白皮书、Demo 和评测报告三类交付。

