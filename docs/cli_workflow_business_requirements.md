# CLI 工作流记忆 — 业务需求

## 1. 业务背景

开发者在不同项目中使用不同的命令行参数组合（如"后台服务部署用 `--env prod --region cn-shanghai --canary 10`"，"数据平台部署用 `--env staging --region us-west-1 --canary 50`"），当前这些知识散落在个人头脑或临时笔记中，每次切换项目需要重新回忆或翻找。

CLI 工作流记忆的目标：**让记忆引擎帮开发者记住"哪个项目、什么场景、用哪些参数"，不用手动查文档**。

## 2. 核心约束

- **个人记忆**：CLI 工作流是开发者个人的命令习惯，不来自群聊讨论，scope 为 `user`
- **双通道注入**：CLI 终端被动监听（隐式记忆）+ OpenClaw 对话显式教学（显式记忆）
- **双通道输出**：CLI 终端查询补全 + OpenClaw 上下文主动推荐
- **复用 MemoryCore**：在统一 MemoryCore 之上建领域记忆，与 project_decision / team_retention 共存

---

## 3. 记忆注入点

### 3.1 CLI 被动监听（隐式注入）

**场景**：开发者正常在终端执行命令，系统通过 shell hook 无感捕获每次执行，自动从中提取高频命令模式和参数习惯。用户无需做任何额外操作。

**交互方式**：

```bash
# 一次性安装 shell hook
$ lark-memory hook install

# 之后正常使用终端，系统自动监听
$ cd project/backend
$ lark project deploy --env prod --region cn-shanghai --canary 10
# ↑ 这条命令被自动捕获并上报，用户无感知
```

**Shell Hook 机制**：

| Shell | 钩子方式 |
|---|---|
| Bash | `trap '_lark_preexec' DEBUG` + `PROMPT_COMMAND` |
| Zsh | `add-zsh-hook preexec` + `add-zsh-hook precmd` |

每次命令执行的生命周期：
1. `preexec` 触发 → 记录命令文本和执行开始时间
2. 命令执行完成
3. `precmd` 触发 → 获取退出码、计算耗时、读取 `cwd`
4. 异步上报到 `POST /api/v1/ingest`（后台进程，不阻塞终端）

**过滤策略**（后端 extractor 层，不上报端过滤）：

并非每一条命令都值得形成长期记忆。`CLIWorkflowExtractor` 按以下规则过滤：

| 条件 | 说明 |
|---|---|
| 无条件跳过 | 纯 `cd`、`ls`、`echo`、`pwd` 等日常浏览命令 |
| 无条件跳过 | 单字命令且无任何参数（如 `git`、`npm` 裸敲） |
| 保留 | 包含 `--` 或 `-` 参数的任意命令 |
| 保留 | 已知工具链前缀：`git`、`docker`、`kubectl`、`npm`、`yarn`、`lark`、`uv` 等 |

**系统行为**：

1. Shell hook 捕获每次命令执行的完整信息（命令文本、退出码、耗时、cwd）
2. 异步发送 `NormalizedEvent`（`event_type=command_finished`，`source_type=shell`）到 `POST /api/v1/ingest`
3. 后端 `CLIWorkflowExtractor` 过滤无意义命令后，从有效命令中提取：
   - **命令模板**：将具体参数值替换为变量位，得到 `lark project deploy --env {env} --region {region} --canary {pct}`
   - **参数绑定**：记录本次执行中每个参数的具体值，累积频率
   - **上下文**：`user_id`（谁执行的）、`project_id`（从 cwd/git remote 推断）、`repo_id`、`cwd`
   - **执行结果**：退出码、耗时、成功/失败
4. 将提取结果写入 `CLIWorkflowMemory` → 转为 `MemoryCore` 入库
5. 同一用户+同一项目+同一命令模板的重复执行走**强化更新**（execution_count++、更新 last_executed_at、刷新参数频率、更新成功率）

**事件结构**：

| 字段 | 值 |
|---|---|
| `event_type` | `command_finished` 或 `command_failed` |
| `source_type` | `shell` |
| `scope` | `user` |
| `content_text` | 完整命令字符串 |
| `payload.command` | 命令名 |
| `payload.args` | 参数列表 |
| `payload.exit_code` | 退出码 |
| `payload.cwd` | 执行时的工作目录 |
| `payload.duration_ms` | 执行耗时 |
| `context.user_id` | 执行用户 |
| `context.project_id` | 从 cwd/git remote 推断的项目标识 |
| `context.repo_id` | 关联仓库 |

### 3.2 OpenClaw 显式教学（显式注入）

**场景**：开发者在与 OpenClaw 的 1:1 对话中，主动告诉它记住某条命令的用法。

**交互方式**：

```
用户: 记住：部署后台服务到 staging 要用 lark project deploy --env staging --canary 50
用户: 以后在这个项目里提到部署，提醒我用 --region cn-shanghai
```

**系统行为**：

1. OpenClaw 插件检测到用户有"记忆教学"意图（关键词：记住/提醒我/以后…用/别忘了），将消息内容构造为 `NormalizedEvent` 发送到 `POST /api/v1/ingest`
2. 后端 `CLIWorkflowExtractor` 从教学文本中提取：
   - **命令模板**：从自然语言中解析出命令骨架
   - **参数绑定**：从自然语言中解析出参数名和取值
   - **上下文**：`user_id`（谁教的）、`project_id`（提及哪个项目）
3. 写入 `CLIWorkflowMemory` → 转为 `MemoryCore` 入库
4. 如果已存在同一用户+同一项目+同一命令的旧记忆，走**显式覆盖**（OpenClaw 教的内容视为用户确认的最新信息）

**事件结构**：

| 字段 | 值 |
|---|---|
| `event_type` | `memory_feedback` |
| `source_type` | `openclaw` |
| `scope` | `user` |
| `content_text` | 用户教学原文 |
| `payload.intent` | `teach_command` |
| `context.user_id` | 教学用户 |
| `context.project_id` | 关联项目（从上下文推断） |

### 3.3 注入路径对比

| 维度 | CLI 被动监听 | OpenClaw 显式教学 |
|---|---|---|
| 记忆类型 | 隐式记忆（系统自动观察） | 显式记忆（用户主动教学） |
| 触发方 | 无需用户操作，shell hook 自动捕获 | 用户在对话中主动教学 |
| 信息完整度 | 完整命令+参数+执行结果 | 自然语言，可能部分参数 |
| 项目上下文 | 从 cwd/git remote 自动推断 | 从对话上下文推断 |
| 可靠性 | 高（机器记录，客观事实） | 中（需解析自然语言） |
| 记忆更新策略 | 频率强化 + 参数渐变（统计驱动） | 显式覆盖（用户意图明确） |
| 用户心智负担 | 零（安装后无感） | 低（想起来时说一声） |
| 优先级 | OpenClaw 教学优先于 CLI 统计（用户明确说 > 机器统计） |

---

## 4. 记忆输出交互场景

### 4.1 CLI Tab 自动补全

**场景**：开发者在终端输入命令前缀后按 Tab，系统根据历史记忆自动补全剩余参数。

**交互方式**：

```bash
# 用户输入部分命令后按 Tab
$ lark project deploy --[Tab]

# 系统根据当前项目上下文 + 记忆，弹出补全候选：
--env prod    --region cn-shanghai    --canary 10
```

**补全层级**：

| 层级 | 触发位置 | 示例 | 补全内容 |
|---|---|---|---|
| 子命令补全 | `lark [Tab]` | `lark ` → `project` | 该工具的子命令名 |
| 参数名补全 | `lark project deploy --[Tab]` | `--` → `--env`, `--region`, `--canary` | 该命令的常用参数名 |
| 参数值补全 | `lark project deploy --env [Tab]` | `--env ` → `prod`, `staging` | 当前项目下该参数的历史取值 |

**系统行为**：

1. 用户在终端输入命令前缀后按 Tab
2. Shell completion script 调用 `lark-memory complete -- "<当前命令行前缀>"`
3. `lark-memory` CLI 调用 `POST /api/v1/retrieve`，传入：
   - `query_text` = 当前命令行前缀
   - `domain` = `cli_workflow`
   - `user_id` = 当前用户
   - `project_id` = 从当前目录推断
   - `context` = 已输入的命令部分（用于补全位置判断）
4. 后端检索匹配的命令记忆，根据光标位置返回对应层级的补全候选
5. CLI 输出候选列表（每行一个），由 shell 渲染为补全菜单

**补全候选的语义标注**：

每个补全候选附带使用频率，shell 按频率降序排列：

```
--env prod          ← 42次 (最近)
--env staging       ← 3次
```

**Shell 集成方式**：

```bash
# 用户在 .bashrc / .zshrc 中添加一行即可启用
source <(lark-memory completion bash)    # bash
source <(lark-memory completion zsh)     # zsh
```

`lark-memory completion <shell>` 子命令动态生成 completion script，其中关键钩子：

```bash
# completion script 核心逻辑 (示意)
_lark_memory_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local line="${COMP_LINE}"
    # 调后端检索记忆，获取补全候选
    local candidates=$(lark-memory complete -- "$line" "$cur")
    COMPREPLY=($candidates)
}
```

### 4.2 CLI 主动查询

**场景**：开发者在终端中想不起某个项目的部署参数，主动查询记忆。

**交互方式**：

```bash
# 按项目+命令关键词查询
lark-memory suggest "deploy 后台服务"

# 按项目查询所有命令记忆
lark-memory suggest --project 后台服务

# 按命令名查询所有项目的参数差异
lark-memory suggest --command "lark project deploy"
```

**系统行为**：

1. CLI 工具调用 `POST /api/v1/retrieve`，传入 `query_text` 和 domain 过滤 `cli_workflow`，以及 user_id、project_id 上下文
2. 后端走 `IntentAnalyzer` → `QueryRewriter` → `CLIWorkflowRetriever` → `Reranker` 检索管线
3. 返回匹配的命令记忆列表，每条包含命令模板、参数绑定、执行频率、最近使用时间

**期望输出格式**：

```
$ lark-memory suggest "deploy 后台服务"

  命令: lark project deploy
  项目: 后台服务
  常用参数:
    --env prod          (42次, 最后: 2026-05-03)
    --region cn-shanghai (42次, 最后: 2026-05-03)
    --canary 10          (38次, 最后: 2026-04-28)

  最近使用: 2026-05-03 14:22
  成功率: 95%
```

### 4.3 OpenClaw 主动推荐

**场景**：开发者在与 OpenClaw 对话讨论部署相关话题时，OpenClaw 自动召回相关命令记忆并推荐。

**交互方式**：

```
用户: 准备部署后台服务了，帮我检查一下

OpenClaw: 根据你的历史记录，部署后台服务通常使用以下命令：
  lark project deploy --env prod --region cn-shanghai --canary 10
  最近 42 次执行，成功率 95%。

  需要我帮你执行吗？
```

**系统行为**：

1. OpenClaw 的 `before_prompt_build` hook 在构造 Agent 提示词前，调用 `POST /api/v1/retrieve` 查询 cli_workflow 记忆
2. 传入当前对话的 `query_text`、`user_id`、`project_id` 上下文
3. 后端检索并返回相关记忆
4. OpenClaw 将召回的记忆注入到 Agent 的 system prompt 或上下文中
5. Agent 在回复时自然引用这些记忆，向用户推荐命令和参数

**注入时机**：

| Hook | 用途 |
|---|---|
| `before_prompt_build` | 根据用户当前消息，检索相关命令记忆，注入到 Agent 上下文 |
| `agent_end` | 将 Agent 回复中用户确认使用的命令作为新事件写回（反馈闭环） |

### 4.4 输出场景对比

| 维度 | CLI Tab 自动补全 | CLI 主动查询 | OpenClaw 主动推荐 |
|---|---|---|---|
| 触发方式 | 按 Tab 触发 | 用户显式执行 `suggest` | 系统自动（对话上下文匹配） |
| 交互形式 | 终端补全菜单 | 终端文本输出 | 对话中的自然语言 |
| 返回内容 | 补全候选（单行列表） | 命令模板 + 参数绑定 + 统计 | 命令模板 + 参数建议 + 自然语言 |
| 上下文感知 | 光标位置 + 当前目录→project | 用户显式指定 | 对话上下文→project |
| 使用门槛 | 零门槛（按 Tab 即可） | 需主动查询 | 零门槛（对话中自然呈现） |

---

## 5. 数据流总览

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  【输入】                     【处理】                   【输出】  │
│                                                                  │
│  CLI shell                   Memory Engine              CLI       │
│  ┌──────────┐               ┌──────────────┐          ┌──────┐  │
│  │shell hook│──ingest──────→│              │          │complete│  │
│  │          │               │              │          │suggest│  │
│  └──────────┘               │ CLIWorkflow  │          └──────┘  │
│                              │ Extractor    │                     │
│  OpenClaw                   │   ↓          │          OpenClaw   │
│  ┌──────────┐               │ CLIWorkflow  │          ┌──────┐  │
│  │ 显式教学  │──ingest──────→│ Memory →     │─retrieve→│ 推荐  │  │
│  └──────────┘               │ MemoryCore   │          └──────┘  │
│                              │   ↓          │                     │
│                              │ SQLite       │                     │
│                              └──────────────┘                     │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. 不做的事

- 不做工作流序列挖掘（前序/后续命令关联）—— 当前聚焦参数绑定，序列模式后续迭代
