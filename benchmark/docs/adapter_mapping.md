# Benchmark Event ↔ LarkMemory API 字段映射规范

> **版本**: v1.0  
> **创建时间**: 2026-05-01  
> **状态**: 规范定义（待 runner 实现时落地）

本文档定义 benchmark 数据集中的事件字段与 LarkMemory 后端 API (`/api/v1/ingest`) 之间的映射关系，是 `run_benchmark.py` 实现 adapter 的参考依据。

---

## 1. 设计原则

1. **Benchmark 数据集不绑定任何特定后端**：数据集使用通用字段，通过 adapter 层转换为后端所需的格式
2. **单向映射**：benchmark event → LarkMemory IngestRequest（评测时不需要反向转换）
3. **Lossless**：映射过程不丢失语义信息；如存在信息损失，必须在 `eval_notes` 中说明

---

## 2. 字段映射表

### 2.1 核心字段

| Benchmark Event 字段 | LarkMemory IngestRequest 字段 | 转换规则 |
|---------------------|-------------------------------|---------|
| `event_id` | `event_id` | 直接映射（格式兼容：双方均使用字符串 ID） |
| `timestamp` | `occurred_at` | 直接映射（ISO 8601 格式） |
| `content` | `content_text` | 直接映射 |
| `speaker` | `context.speaker` | 嵌入 context 对象 |
| `context.project` | `context.project_id` | 重命名为 project_id |
| `context.user` | `context.user_id` | 重命名为 user_id |
| `context.team` | `context.team_id` | 重命名为 team_id |

### 2.2 source → source_type + event_type 映射

| Benchmark `source` | LarkMemory `source_type` | LarkMemory `event_type` | 说明 |
|-------------------|-------------------------|------------------------|------|
| `cli` | `shell` | `command_finished` | CLI 命令执行完成 |
| `feishu_group` | `feishu_chat` | `chat_message` | 飞书群聊消息 |
| `feishu_chat` | `feishu_chat` | `chat_message` | 飞书单聊消息 |
| `feishu_doc` | `feishu_doc` | `doc_changed` | 飞书文档变更 |
| `feishu_task` | `task_system` | `task_updated` | 飞书任务状态变更 |
| `feishu_meeting` | `meeting` | `meeting_note` | 飞书会议纪要 |

### 2.3 转换示例

**Benchmark Event:**
```json
{
  "event_id": "e1",
  "timestamp": "2026-04-15T10:30:00Z",
  "source": "feishu_group",
  "speaker": "张工",
  "content": "我们决定把缓存层从 Redis 切换到 Memcached，Redis 内存占用太高了",
  "context": {
    "project": "LarkMemory",
    "team": "后端组"
  }
}
```

**转换后的 LarkMemory IngestRequest:**
```json
{
  "event_id": "e1",
  "event_type": "chat_message",
  "source_type": "feishu_chat",
  "occurred_at": "2026-04-15T10:30:00Z",
  "content_text": "我们决定把缓存层从 Redis 切换到 Memcached，Redis 内存占用太高了",
  "context": {
    "project_id": "LarkMemory",
    "team_id": "后端组",
    "speaker": "张工"
  }
}
```

---

## 3. 跨项目隔离测试的特殊处理

cross_project 类型的 case 涉及多个项目的事件，adapter 需要：

1. **按项目分组 ingest**：每个项目的事件使用不同的 `context.project_id`
2. **记录项目边界**：维护 `{project_id: [event_ids]}` 映射表
3. **查询时指定作用域**：retrieve 请求中携带 `context.project_id`，验证系统是否只在正确作用域内返回记忆

```
示例流程：
1. ingest events with project_id="Alpha" → [e1, e2, e3]
2. ingest events with project_id="Beta"  → [e4, e5, e6]
3. retrieve with project_id="Beta"       → 应只返回 Beta 项目的记忆
4. score: scope_accuracy = 是否全部返回的记忆都属于 Beta
```

---

## 4. 补充评测协议

### 4.1 Paired Sentinel Case（可选增强）

主评测采用 noisy 单场景判分。如需在答辩中展示更严谨的抗干扰量化结果，可补充少量 paired sentinel case：

| 评测模式 | 说明 | 适用场景 |
|---------|------|---------|
| **noisy 单场景**（主评测） | 直接在含噪声的事件集上判分 | 所有 anti_interference case |
| **clean/noisy 配对**（补充评测） | 同一 case 分别用 clean 和 noisy 事件集运行，计算 `robustness_ratio = noisy_score / clean_score` | 每个方向选取 1 条 sentinel case |

配对 sentinel case 不需要大规模实施，每个方向 1 条即可在答辩中展示方法论的严谨性。

### 4.2 LLM-as-Judge 适配

当使用 LLM-as-Judge 判分（v1 阶段）时，adapter 需要额外：
1. 将 LarkMemory 的 retrieve 响应转换为 LLM 判分 prompt 的输入格式
2. 将判分 prompt 的输出映射回 benchmark 的指标体系

---

## 5. 待确认项

以下事项需在 runner 实现前与 LarkMemory 后端对齐：

- [ ] LarkMemory `/api/v1/retrieve` 是否支持按 `project_id` 过滤（cross_project 评测必需）
- [ ] LarkMemory 的 context 字段是否支持自定义 key（如 `speaker`、`team_id`）
- [ ] IngestRequest 是否有 batch 接口（当前假设为逐条 ingest）
- [ ] 是否支持在 ingest 前清空/隔离数据库（评测隔离性必需）
