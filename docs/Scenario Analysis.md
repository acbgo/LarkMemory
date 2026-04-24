# 四个探索方向的 Agent 事件交互链路

## 一、方案定位

本项目采用 `TypeScript OpenClaw 插件 + Python 长期记忆后端` 的旁路架构。

- TypeScript 插件不替换 OpenClaw 原有记忆引擎。
- 插件负责监听 Agent 生命周期、工具调用、命令执行以及飞书侧事件。
- Python 后端作为旁路长期记忆引擎，负责记忆的提取、存储、检索、更新、遗忘与主动服务。

四个探索方向共用一套统一的记忆平台，但每个方向使用独立的：

- `memory domain`
- 抽取逻辑
- 检索排序策略
- 主动触发策略

因此，对外应表述为：`一个统一的企业级长期记忆平台，支撑四种场景化记忆模式。`

---

## 二、统一的 Agent-Memory 闭环

四个方向共享同一条高层闭环链路：

```text
OpenClaw Agent / 外部事件
-> TS 插件捕获生命周期、工具调用、消息上下文
-> 事件标准化
-> Python Memory Engine 接收 ingest
-> 路由到对应 memory domain
-> 提取结构化记忆
-> 冲突检测 / 版本覆盖 / 衰减策略绑定
-> 写入记忆存储与索引

后续新的 Agent Run / 用户查询 / 定时触发
-> TS 插件发起 memory query
-> Python Memory Engine 检索与重排
-> 结果注入 prompt / tool context / 卡片建议
-> Agent 在记忆辅助下完成行动
-> 用户反馈与执行结果继续反写，形成强化闭环
```

推荐的记忆注入时机：

- `before_prompt_build`：规划级记忆注入
- `before_tool_call`：执行级记忆注入
- `after_tool_result` 或命令完成：记忆学习与更新
- `scheduler / event bus`：主动提醒与主动服务触发

---

## 三、方向 A：CLI 工作流记忆

## 1. 场景定义

方向 A 不应定义为“终端逐字输入补全”，而应定义为：

`面向 OpenClaw Agent 的 CLI 工作流长期记忆`

系统记住的不是用户正在输入的字符，而是：

- 常用命令模板
- 参数偏好
- repo / workspace 绑定关系
- 多步工作流模式
- 历史成功与失败经验

## 2. 需要设计的记忆类型

- `command_template`：命令模板记忆
- `param_preference`：参数偏好记忆
- `workflow_pattern`：工作流序列记忆
- `context_binding`：上下文绑定记忆
- `execution_outcome`：执行结果记忆

## 3. Agent 事件交互链路

```text
用户要求 OpenClaw 帮忙部署 / 构建 / 排障
-> Agent 进入规划阶段
-> TS 插件在 before_prompt_build 发起记忆检索
-> 查询当前 repo / 项目 / 任务相关的 CLI 工作流记忆
-> Python 返回历史工作流摘要、常用命令模板、最佳参数组合
-> 插件把结果注入当前 prompt 上下文
-> Agent 形成执行计划

Agent 即将调用 shell / command 工具
-> TS 插件在 before_tool_call 再发起一次执行级检索
-> 结合 repo + cwd + 当前动作查询更细粒度记忆
-> Python 返回命令模板建议、参数提醒、风险提示、下一步动作建议
-> 插件注入 tool 级上下文
-> 命令开始执行

命令执行结束
-> TS 插件捕获 command、args、cwd、repo、结果、耗时
-> 发送 ingest 事件给 Python 后端
-> Python 提取命令模板、参数槽位、工作流序列、成功信号
-> 完成记忆去重、合并、打分更新
-> 写入 CLI 工作流记忆库

后续出现相似任务
-> 再次利用这些记忆为 Agent 提供规划支持与主动建议
```

## 4. 什么时候抽取与存储

- 命令成功执行后
- 同类命令重复达到阈值后
- 一段多步工作流完成后
- 用户纠正命令或参数选择后

## 5. 什么时候触发主动服务

- 相似任务开始时
- Agent 即将调用 shell 工具时
- 某一步完成后，下一步具有明显模式时
- 即将重复发生历史高风险失败路径时

## 6. 后端记忆引擎运行链路

```text
Hook / Event
-> ingest router 判断 domain = cli_workflow
-> 命令解析器提取 command template 与参数槽位
-> workflow miner 识别前后步骤关系
-> scorer 更新 recency / frequency / success rate
-> 写入结构化 CLI 记忆与索引
-> retrieve 时以 repo / task / cwd 作为核心检索键
-> proactive service 输出流程推荐与安全默认值
```

---

## 四、方向 B：项目决策与上下文记忆

## 1. 场景定义

方向 B 要做的不是普通聊天召回，而是：

`结构化的项目决策记忆`

系统需要记住：

- 做了什么决策
- 决策原因是什么
- 放弃了哪些备选方案
- 是谁做出的决定
- 在什么项目阶段、什么时间点生效

## 2. 需要设计的记忆类型

- `project_decision`：项目决策记忆
- `decision_rationale`：决策理由记忆
- `rejected_alternative`：被否决方案记忆
- `milestone_deadline`：里程碑与截止时间记忆
- `decision_version`：决策版本记忆

## 3. Agent 事件交互链路

```text
飞书群聊 / 文档 / 会议纪要中发生项目讨论
-> TS 插件捕获消息或文档变更事件
-> 标准化后发送给 Python 后端
-> 后端识别是否包含决策语义
-> 抽取 topic、options、final decision、rationale、owner、deadline、stage
-> 与历史项目决策记忆做比对
-> 创建新决策，或覆盖旧版本决策
-> 写入结构化项目决策记忆

后续相关议题再次出现
-> Agent 准备回答或总结
-> TS 插件在 before_prompt_build 查询决策记忆
-> 以 project + topic + entities + current phase 为检索条件
-> Python 返回当前有效决策卡片以及被覆盖的历史决策链
-> 插件将结果注入上下文
-> Agent 在回答中引用正确的历史决策背景

若出现新的结论推翻旧决策
-> 新事件进入 ingest
-> 后端标记旧决策为 superseded
-> 新版本成为当前 active 决策
-> 后续所有召回都优先返回最新有效版本
```

## 4. 什么时候抽取与存储

- 群聊或文档中出现明显决策语义时
- 会议纪要生成后
- 里程碑、截止日期被确认后
- 任务审批、拒绝或阶段状态变化后

## 5. 什么时候触发主动服务

- 相关话题再次被讨论时
- 已被否决的方案再次被提出时
- 项目进入新阶段，需要回顾历史决策时
- 有人询问“为什么当时这么决定”时

## 6. 后端记忆引擎运行链路

```text
Hook / Event
-> ingest router 判断 domain = project_decision
-> 决策语义分类器识别内容类型
-> extractor 构造结构化 decision 对象
-> conflict resolver 按时序判断是否 supersede
-> 写入当前 active 决策与历史版本链
-> retrieve 时按 topic / project / stage 检索
-> proactive service 向当前讨论推送历史决策卡片
```

---

## 五、方向 C：个人习惯与偏好记忆

## 1. 场景定义

方向 C 的目标不是做简单用户画像，而是：

`个性化主动服务记忆`

系统需要逐步学习用户的：

- 稳定偏好
- 周期性习惯
- 常见操作方式
- 可抽象成规则的重复行为

## 2. 需要设计的记忆类型

- `user_preference`：用户偏好记忆
- `routine_pattern`：周期习惯记忆
- `automation_rule`：自动化规则记忆
- `correction_feedback`：用户纠正反馈记忆

## 3. Agent 事件交互链路

```text
用户在飞书 / OpenClaw 中反复执行相似行为
-> TS 插件捕获视图选择、提醒行为、日历动作、任务习惯、纠正反馈
-> 标准化后发送给 Python 后端
-> 后端识别重复模式、周期特征、稳定偏好
-> 生成 preference 或 routine 候选项
-> 当候选置信度超过阈值
-> 存入长期个人记忆

后续出现相似上下文
-> before_prompt_build 或定时触发器被触发
-> 插件按 user + time + task + context 查询个人记忆
-> Python 返回匹配的 preference / routine / rule
-> 插件将结果注入 prompt 或提醒卡片
-> Agent 按用户习惯提供个性化服务

用户接受或拒绝建议
-> 反馈回流后端
-> 更新该偏好或规则的置信度
```

## 4. 什么时候抽取与存储

- 某行为重复次数达到阈值后
- 形成稳定的日/周周期模式后
- 用户多次纠正 Agent 输出后
- 用户明确表达“以后都这样做”后

## 5. 什么时候触发主动服务

- 周期性会议、周报、例行任务开始前
- 相似任务上下文再次出现时
- Agent 需要在多个默认选项中做选择时
- 可以预填、预设或提醒时

## 6. 后端记忆引擎运行链路

```text
Hook / Event
-> ingest router 判断 domain = personal_preference
-> temporal miner 识别周期模式
-> preference extractor 生成标准化 preference slot 或 routine rule
-> scorer 计算稳定性与置信度
-> 写入个人偏好 / 习惯 / 规则记忆
-> retrieve 时按用户当前上下文匹配
-> proactive service 输出提醒、预填建议、个性化默认值
```

---

## 六、方向 D：团队知识断层与遗忘预警记忆

## 1. 场景定义

方向 D 最符合题目中对 `遗忘、覆盖、主动提醒` 的强调。

它关注的是：

`团队必须长期保留、但会随着时间被遗忘的关键事实`

系统需要记住：

- 团队关键事实
- 风险等级与负责人
- 复习计划与遗忘曲线
- 版本替换关系

## 2. 需要设计的记忆类型

- `team_critical_fact`：团队关键事实记忆
- `review_schedule`：复习计划记忆
- `fact_version`：事实版本记忆
- `risk_alert`：风险预警记忆

## 3. Agent 事件交互链路

```text
团队在飞书 / 文档 / 任务流中提到关键事项
-> TS 插件捕获相关事件或手动 remember 动作
-> 发送到 Python 后端
-> 后端识别高价值、易遗忘的团队事实
-> 抽取 fact content、scope、risk、owner、expiry、review cycle
-> 生成结构化共享记忆，并绑定遗忘策略
-> 写入当前有效版本与下一次复习计划

时间推进，或相关话题再次出现
-> scheduler 或对话触发器被激活
-> 插件查询团队长期记忆
-> Python 检查是否到达复习时间、是否临近过期、是否存在上下文相关性
-> 若达到触发条件，则生成主动提醒卡片
-> 插件把提醒推送到群聊、Agent 上下文或项目界面

若新信息覆盖旧事实
-> 后端比较版本关系
-> 将旧事实标记为 inactive / superseded
-> 新事实重建 review schedule
```

## 4. 什么时候抽取与存储

- 团队显式注入长期记忆时
- 高风险事实被讨论时
- API key、客户约束、合规要求、截止日期等被更新时
- 新成员需要 onboarding 关键知识时

## 5. 什么时候触发主动服务

- 到达复习时间时
- 记忆临近失效或遗忘风险升高时
- 相关讨论再次出现时
- 即将执行高风险操作时
- 新成员加入项目时

## 6. 后端记忆引擎运行链路

```text
Hook / Event
-> ingest router 判断 domain = team_retention
-> critical fact detector 抽取结构化事实
-> review planner 生成复习与遗忘策略
-> version manager 判断覆盖与失效关系
-> 写入事实记忆与 review schedule
-> scheduler 定时扫描待提醒项
-> proactive service 向当前群聊 / Agent / 看板推送提醒
```

---

## 七、跨域协同策略

虽然四个方向拥有不同的业务语义，但整体必须以“一套统一平台”来设计和展示。

推荐实现策略：

- 一个统一 ingest API
- 一个统一 retrieve API
- 一个共享的核心 metadata 模型
- 一套统一的 lifecycle 管理
- 多个 domain-specific extractor、ranker、trigger policy

跨域联动示例：

- 部署任务：
  - 主查 `cli_workflow`
  - 可辅查 `team_retention`

- 项目复盘：
  - 主查 `project_decision`
  - 可辅查 `team_retention`

- 个性化任务安排：
  - 主查 `personal_preference`

---

## 八、建议的比赛表述

为了让评委理解你们做的是“平台”而不是“四个散装 Demo”，建议将四个方向包装为四种 `memory mode`：

- `Mode A`：CLI 工作流记忆
- `Mode B`：项目决策记忆
- `Mode C`：个人偏好记忆
- `Mode D`：团队长期保留记忆

统一对外表述为：

`我们基于 OpenClaw 生命周期 Hook 构建了一套旁路式企业级长期记忆平台，支持不同业务场景下的记忆提取、存储、检索、更新、遗忘与主动服务。`
