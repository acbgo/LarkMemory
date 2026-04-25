# LarkMemory 方向 C & D 任务流程规划

## Context

本项目构建飞书企业级长程协作 Memory 系统。方向 C（个人偏好记忆）和方向 D（团队遗忘预警）主要对应用户在飞书端的个性化体验和团队知识管理需求。技术栈：Python + FastAPI 后端 + 飞书 API + OpenClaw 插件 hook 调用。Demo 需同时支持 CLI 和飞书端交互。

---

## 一、方向 C：个人工作习惯与偏好记忆

### 1.1 记忆定义（Define）

| 记忆类型 | 来源 | 示例 |
|---------|------|------|
| 显式偏好 | 用户主动告知 | "我喜欢表格视图"、"周报模板用B" |
| 隐式偏好 | 系统观察统计 | 用户90%的时间选择表格视图（而非列表） |
| 工作节奏 | 日程+行为模式 | "每周五下午3点整理周报" |
| 操作习惯 | 高频操作序列 | "开会前必看文档X"、"新建任务总是先建文档再建群" |

### 1.2 任务流程

```
┌─────────────────────────────────────────────────────────┐
│                    数据采集层                             │
│  飞书事件订阅 → 消息事件 / 日程事件 / 文档操作 / 审批动作  │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    行为提取层                             │
│  原始事件 → 频率统计 + LLM语义提取 → 行为模式候选         │
│  例：观察到"每周五14:00打开周报文档" → 候选规则            │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  偏好确认与存储                            │
│  候选规则 → 置信度评估                                    │
│    ├─ 高置信（频率>阈值）→ 自动写入偏好记忆               │
│    └─ 低置信 → 通过飞书消息向用户确认 "我注意到你经常…？"  │
│  存储为结构化偏好槽位：{ slot, value, confidence, source } │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  规则生成引擎                             │
│  偏好记忆 → 可执行规则                                    │
│  例：{slot:"周报时间", value:"周五15:00"} →              │
│      规则：每周五14:55提醒"该整理周报了"                   │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  主动服务层                               │
│  ├─ 定时触发：cron调度 → 飞书机器人推送提醒/自动化         │
│  ├─ 上下文触发：检测到"开会"→ 主动推送相关材料            │
│  └─ 偏好应用：对话/展示时自动应用已记录的偏好格式          │
└─────────────────────────────────────────────────────────┘
```

### 1.3 数据模型

```python
# 偏好记忆
class PreferenceMemory:
    id: str
    user_id: str
    slot: str              # 偏好槽位，如 "report_time", "view_preference"
    value: str             # 偏好值
    confidence: float      # 置信度 0-1
    source: str            # "explicit" | "implicit"
    evidence_count: int    # 观察次数
    created_at: datetime
    updated_at: datetime
    superseded_by: str | None  # 被哪条记忆覆盖

# 行为规则
class BehaviorRule:
    id: str
    user_id: str
    trigger_type: str      # "cron" | "event" | "context"
    trigger_config: dict   # 触发条件配置
    action_type: str       # "remind" | "suggest" | "auto_execute"
    action_config: dict    # 执行动作配置
    from_preference_id: str
    enabled: bool
```

### 1.4 API 设计

```
POST   /api/v1/preferences              # 存入偏好
GET    /api/v1/preferences/{user_id}     # 查询用户偏好
PUT    /api/v1/preferences/{id}          # 更新偏好
DELETE /api/v1/preferences/{id}          # 删除偏好

POST   /api/v1/behaviors/observe         # 上报行为事件
GET    /api/v1/behaviors/patterns/{uid}   # 获取行为模式

POST   /api/v1/rules                     # 创建规则
GET    /api/v1/rules/{user_id}           # 查询用户规则
PUT    /api/v1/rules/{id}/toggle         # 启用/禁用规则

GET    /api/v1/suggestions/{user_id}     # 获取当前上下文的个性化建议
```

### 1.5 开发任务分解

| 序号 | 任务 | 依赖 | 优先级 |
|------|------|------|--------|
| C1 | 搭建 FastAPI 项目骨架 + 数据库模型（SQLite/PostgreSQL） | 无 | P0 |
| C2 | 实现偏好记忆 CRUD API | C1 | P0 |
| C3 | 飞书事件订阅接入（消息、日程、文档事件） | C1 | P0 |
| C4 | 行为事件上报与存储 | C1 | P1 |
| C5 | 频率统计模块（从原始事件中聚合模式） | C4 | P1 |
| C6 | LLM 偏好提取模块（从对话中提取显式偏好） | C2 | P1 |
| C7 | 偏好确认交互流程（低置信度时飞书确认） | C2, C3 | P2 |
| C8 | 规则生成引擎（偏好→可执行规则） | C2, C5 | P2 |
| C9 | 定时调度器（cron触发规则执行） | C8 | P2 |
| C10 | 上下文触发引擎（事件驱动的主动建议） | C8, C3 | P3 |
| C11 | 飞书消息推送集成 | C3 | P1 |
| C12 | CLI 查询/管理偏好命令 | C2 | P2 |

---

## 二、方向 D：团队知识断层与遗忘预警

### 2.1 记忆定义（Define）

| 记忆类型 | 来源 | 示例 |
|---------|------|------|
| 团队决策 | 群聊/文档讨论 | "确认使用方案B而非A，理由是性能优30%" |
| 关键事项 | 团队成员主动注入 | "API密钥已更新为xxx"、"客户要求改用JSON格式" |
| 操作规范 | 项目约定 | "部署前必须通过staging验证" |
| 时效信息 | 带有效期的事项 | "截止日期是5号"、"Q3预算审批已通过" |

### 2.2 任务流程

```
┌─────────────────────────────────────────────────────────┐
│                  记忆注入层                               │
│  ├─ 显式注入：团队成员通过飞书命令/CLI主动添加             │
│  │   例：@记忆助手 记住：以后周报发给张三                  │
│  ├─ 自动提取：从群聊讨论中LLM提取决策/结论                │
│  └─ 元数据标注：重要度、有效期、关联项目、关联人           │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│                版本管理与冲突检测                          │
│  新记忆写入时：                                          │
│    ├─ 语义相似度检索 → 发现潜在冲突                       │
│    ├─ 无冲突 → 正常写入                                  │
│    ├─ 有冲突 + 新信息更新 → 标记旧记忆为superseded        │
│    └─ 有冲突 + 不确定 → 人工确认                         │
│  版本链：v1(superseded) → v2(superseded) → v3(active)    │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│               遗忘曲线引擎                                │
│  基于Ebbinghaus模型：                                    │
│    strength = initial × e^(-λ × t)                      │
│    其中 t = 距上次复习的时间                              │
│          λ 由重要度、团队规模、访问频率决定                │
│  复习一次 → strength 重置为 initial × boost_factor       │
│  多次被引用 → boost_factor 递增（记忆越重要衰减越慢）     │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│              复习提醒调度                                  │
│  定时扫描所有团队记忆的 strength：                        │
│    ├─ strength < 阈值1(弱) → 群聊提醒                    │
│    │   "大家注意：[API密钥已更新]，请确认是否仍然有效"     │
│    ├─ strength < 阈值2(极弱) → 私聊提醒负责人            │
│    └─ strength = 0 且超过有效期 → 标记归档               │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│              记忆召回与推送                                │
│  当群聊讨论触及相关话题时：                               │
│    ├─ 实时语义匹配群聊消息与团队记忆                      │
│    ├─ 命中高相关记忆 → 主动推送"历史决策卡片"             │
│    └─ 卡片格式：[决策] + [理由] + [时间] + [参与者]       │
└─────────────────────────────────────────────────────────┘
```

### 2.3 数据模型

```python
# 团队共享记忆
class TeamMemory:
    id: str
    team_id: str
    version: int                # 版本号
    content: str                # 记忆内容
    category: str               # "decision" | "key_fact" | "standard" | "temporal"
    importance: float           # 重要度 1-5
    expires_at: datetime | None # 有效期（可选）
    strength: float             # 当前记忆强度（遗忘曲线）
    initial_strength: float     # 初始强度
    decay_rate: float           # 衰减速率 λ
    review_count: int           # 被复习次数
    last_reviewed_at: datetime  # 上次复习时间
    superseded_by: str | None   # 被哪个版本覆盖
    source_message_id: str | None  # 来源消息
    participants: list[str]     # 相关参与人
    project_id: str | None      # 关联项目
    embedding: list[float]      # 向量
    created_at: datetime
    updated_at: datetime

# 记忆复习记录
class MemoryReview:
    id: str
    memory_id: str
    review_type: str            # "auto_remind" | "user_confirm" | "context_recall"
    channel: str                # "group_chat" | "private_chat" | "cli"
    response: str | None        # 用户反馈："still_valid" | "outdated" | "updated"
    reviewed_at: datetime

# 记忆版本链
class MemoryVersionChain:
    memory_id: str              # 基础ID（不变）
    versions: list[str]         # 各版本的 memory id
    current_version: str        # 当前生效版本
```

### 2.4 API 设计

```
# 团队记忆管理
POST   /api/v1/team-memories                    # 注入团队记忆
GET    /api/v1/team-memories/{team_id}           # 查询团队记忆列表
GET    /api/v1/team-memories/{team_id}/search    # 语义搜索团队记忆
PUT    /api/v1/team-memories/{id}                # 更新记忆（自动版本管理）
DELETE /api/v1/team-memories/{id}                # 归档记忆

# 版本管理
GET    /api/v1/team-memories/{id}/versions       # 查看版本链
POST   /api/v1/team-memories/{id}/supersede      # 显式覆盖旧记忆

# 遗忘曲线
GET    /api/v1/team-memories/{team_id}/decay-status   # 查看衰减状态
POST   /api/v1/team-memories/{id}/review              # 记录复习事件
POST   /api/v1/team-memories/schedule-reviews          # 触发提醒调度

# 实时召回（飞书群聊hook调用）
POST   /api/v1/team-memories/match                  # 匹配当前话题相关记忆
```

### 2.5 开发任务分解

| 序号 | 任务 | 依赖 | 优先级 |
|------|------|------|--------|
| D1 | 团队记忆数据模型 + CRUD API | 无(P0骨架) | P0 |
| D2 | 向量化存储（ChromaDB集成）+ 语义搜索 | D1 | P0 |
| D3 | 记忆注入接口（显式命令解析） | D1 | P0 |
| D4 | LLM 决策提取模块（从群聊自动提取） | D2 | P1 |
| D5 | 版本管理与冲突检测 | D1 | P1 |
| D6 | 遗忘曲线引擎（Ebbinghaus模型计算） | D1 | P1 |
| D7 | 复习提醒调度器（定时扫描+触发） | D6 | P2 |
| D8 | 飞书群聊提醒推送 | D7 | P2 |
| D9 | 飞书私聊提醒推送 | D7 | P2 |
| D10 | 话题匹配与历史决策卡片推送 | D2 | P2 |
| D11 | CLI 管理命令（注入/查询/状态） | D1 | P2 |
| D12 | 记忆复习反馈处理 | D6, D8 | P3 |

---

## 三、共享基础设施（C & D 共用）

| 序号 | 任务 | 说明 | 优先级 |
|------|------|------|--------|
| I1 | FastAPI 项目初始化 | 目录结构、配置管理、日志 | P0 |
| I2 | 飞书 Bot 基础集成 | 事件订阅、消息发送、OAuth | P0 |
| I3 | 向量数据库集成 | ChromaDB/Milvus + Embedding | P0 |
| I4 | LLM 调用封装 | 统一 LLM 接口，支持多 provider | P0 |
| I5 | OpenClaw 插件 Hook | CLI ↔ Memory API 的桥接 | P1 |
| I6 | Embedding 模型接入 | 文本向量化服务 | P1 |

---

## 四、项目目录结构

```
LarkMemory/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py                # 配置管理
│   │   ├── models/
│   │   │   ├── preference.py        # 偏好记忆模型
│   │   │   ├── team_memory.py       # 团队记忆模型
│   │   │   ├── behavior.py          # 行为事件模型
│   │   │   └── review.py            # 复习记录模型
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── preferences.py   # 偏好 API
│   │   │   │   ├── team_memories.py # 团队记忆 API
│   │   │   │   └── health.py        # 健康检查
│   │   │   └── deps.py              # 依赖注入
│   │   ├── services/
│   │   │   ├── preference_engine.py # 偏好提取与规则生成
│   │   │   ├── decay_engine.py      # 遗忘曲线引擎
│   │   │   ├── version_manager.py   # 版本管理与冲突检测
│   │   │   ├── reminder_scheduler.py# 提醒调度器
│   │   │   └── llm_service.py       # LLM 调用服务
│   │   ├── core/
│   │   │   ├── vector_store.py      # 向量存储封装
│   │   │   ├── embedder.py          # 向量化
│   │   │   └── lark_client.py       # 飞书 API 客户端
│   │   └── workers/
│   │       ├── event_consumer.py    # 飞书事件消费
│   │       ├── decay_worker.py      # 衰减计算定时任务
│   │       └── reminder_worker.py   # 提醒推送定时任务
│   ├── tests/
│   │   ├── test_preferences.py
│   │   ├── test_decay.py
│   │   ├── test_version.py
│   │   └── test_benchmark.py        # 自证评测
│   ├── requirements.txt
│   └── Dockerfile
├── openclaw-plugin/                 # OpenClaw 插件
│   ├── hooks/
│   │   ├── post_command.py          # 命令后 hook（行为采集）
│   │   └── pre_response.py          # 响应前 hook（记忆注入）
│   └── config.json
├── lark-bot/                        # 飞书机器人
│   ├── app.py                       # 机器人入口
│   ├── handlers/
│   │   ├── message_handler.py       # 消息处理
│   │   └── command_handler.py       # 命令处理
│   └── cards/                       # 消息卡片模板
├── docs/
│   ├── DEVELOPMENT PLAN.md
│   ├── DIRECTION_C_D_PLAN.md        # 本文档
│   ├── ARCHITECTURE.md              # 架构白皮书
│   └── BENCHMARK.md                 # 评测报告
└── README.md
```

---

## 五、开发阶段规划

### Phase 1：基础设施 + 核心数据模型（1周）
- I1 FastAPI 项目初始化
- I2 飞书 Bot 基础集成
- I3 向量数据库集成
- I4 LLM 调用封装
- C1 数据库模型搭建
- D1 团队记忆 CRUD

### Phase 2：方向C核心链路（1周）
- C2 偏好记忆 API
- C3 飞书事件订阅接入
- C4 行为事件上报
- C5 频率统计模块
- C6 LLM 偏好提取

### Phase 3：方向D核心链路（1周）
- D2 向量语义搜索
- D3 记忆注入接口
- D5 版本管理与冲突检测
- D6 遗忘曲线引擎
- D7 提醒调度器

### Phase 4：集成与主动服务（1周）
- C8 规则生成引擎
- C9 定时调度器
- D8/D9 飞书提醒推送
- D10 话题匹配与卡片推送
- I5 OpenClaw 插件 Hook

### Phase 5：评测与文档（3天）
- 抗干扰测试用例
- 矛盾更新测试用例
- 效能指标验证
- 架构白皮书撰写
- Demo 录制

---

## 六、评测设计

### 6.1 抗干扰测试
```
步骤：
1. 注入关键记忆M1（如"API密钥已更新为sk-xxx"）
2. 注入50条无关记忆（日常闲聊、其他项目信息）
3. 等待模拟时间7天
4. 查询"当前API密钥是什么"
5. 验证：M1应排在检索结果Top-1，且强度未衰减到提醒阈值以下
指标：命中率、排序位置、响应时间
```

### 6.2 矛盾更新测试
```
步骤：
1. 注入M1："以后周报发给张三"
2. 注入M2："不对，以后周报发给李四"
3. 查询"周报发给谁？"
4. 验证：
   - 系统回答"李四"（而非张三）
   - M1被标记为superseded
   - 版本链正确：M1(v1,superseded) → M2(v2,active)
指标：覆写准确率、版本链完整性
```

### 6.3 效能指标验证
```
方向C：
- 对比"有偏好记忆"vs"无偏好记忆"的操作步数
- 例：设置周报提醒：有记忆=1步（自动触发），无记忆=5步（手动设置）
- 命中率：推荐建议被采纳的比例

方向D：
- 遗忘预警准确率：提醒的信息中仍然有效的比例
- 知识找回率：被遗忘曲线拯救的关键信息数量
- 版本覆写正确率：冲突更新后输出正确版本的比例
```

---

## 七、验证方式

1. **单元测试**：每个核心模块（偏好提取、遗忘曲线、版本管理）的独立测试
2. **集成测试**：通过飞书机器人发送消息，验证端到端链路
3. **CLI 测试**：通过 OpenClaw 插件 hook 调用 Memory API，验证双向互通
4. **Benchmark 脚本**：`tests/test_benchmark.py` 自动化运行评测用例并生成报告
