# LarkMemory AI 协作说明

## 项目背景

LarkMemory 是飞书 AI 比赛 OpenClaw 赛道下的项目，课题是“企业级长程协作 Memory 系统”。

赛道定位是在飞书里“养虾”，让 AI 拥有长时记忆与主动服务能力，打造专属办公 Agent 伙伴。本项目聚焦企业跨部门长程协作中的智能体“失忆”、信息与协作断层等问题，基于飞书 OpenClaw、飞书 CLI、飞书生态与大模型能力，构建具备全流程记忆管理的企业级记忆引擎。

当前项目采用“OpenClaw TypeScript 插件 + 本地 Python Memory Engine 后端服务”的旁路架构。插件负责连接 OpenClaw、采集上下文、触发检索和回传事件；Python Memory Engine 负责记忆的提取、存储、检索、更新、遗忘和主动服务。

当前插件调用链已经通过 mock 输出 log 的方式跑通。现阶段重点是拆解并实现 Memory Engine，同时准备比赛交付物：Memory 定义与架构白皮书、可运行 Demo、自证评测报告。

## 技术栈

- 后端：Python，当前以 dataclass schema、本地 store、retrieval 组件和单元测试为主。
- 插件：TypeScript OpenClaw 插件，代码位于 `plugin/`。
- 存储：本地文件/JSON 存储起步，后续可扩展数据库或向量索引。
- 测试：pytest，测试位于 `tests/`。
- 文档：中文优先，项目长期上下文位于 `memory-bank/`。

## 代码规范

- 修改代码前必须先阅读相关测试，理解当前行为和边界。
- 每次功能改动都要补充或更新单元测试。
- 公共 schema、事件字段、MemoryCore 字段或 store 契约变更时，必须同步更新测试和相关文档。
- 优先沿用现有 dataclass、store、retrieval 组件和 pytest 风格。
- 复杂能力必须拆成可验证的小任务，例如 schema、store、retrieval、service、API、plugin integration。
- 中文文档优先；关键设计、实施计划和进度写入 `memory-bank/`。
- 阶段性工作完成后更新 `memory-bank/progress.md`。

## 禁止事项

- 禁止重构未授权模块。
- 禁止在当前阶段做云端服务。
- 禁止在当前阶段做完整 UI。
- 禁止在当前阶段做生产级认证权限。
- 禁止为了未来扩展提前引入复杂框架或重依赖。
- 禁止直接改动用户已有未提交代码，除非任务明确需要。
