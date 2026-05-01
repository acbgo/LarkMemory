# LarkMemory Benchmark

> 飞书 OpenClaw 赛道 — 企业级长程协作 Memory 系统 评测数据集  
> **Benchmark Version**: v1.0 (4-direction × 7 test-type structure, 49 cases)

---

## 设计理念

本 benchmark 不以"短文本问答准确率"为核心，而以**企业协作记忆的真实可用性**为目标。围绕飞书日常协作中的决策沉淀、偏好学习、命令复用和知识健康场景，构造包含噪声干扰、时序变化、矛盾更新、项目隔离、拒答和效能验证的多维测试集。

本 benchmark 按**比赛文档的四个业务方向**（A/B/C/D）组织为 4 个独立 benchmark，每个 benchmark 内部包含该方向适用的**测试类型**。

> **为什么按方向而不是按测试类型分？**
> 比赛文档定义了 4 个探索方向（CLI 命令记忆、飞书决策记忆、个人偏好记忆、团队知识健康），同时要求至少包含 3 类测试（抗干扰、矛盾更新、效能验证）。每个方向不一定适用所有测试类型（例如 CLI 命令是规律统计，不存在矛盾更新），因此按方向分 benchmark 更合理，每个内部标注适用的测试类型和占比。

---

## Benchmark 总览

| Benchmark | 比赛方向 | 测试类型分布 | 条数 |
|-----------|---------|-------------|------|
| **command_memory** | A：CLI 高频命令与工作流记忆 | 召回 40% · 效能 20% · 抗干扰 20% · 跨项目 20% | 11 |
| **decision_memory** | B：飞书项目决策与上下文记忆 | 召回 15% · 抗干扰 15% · 矛盾更新 15% · 效能 8% · 长时序 8% · 拒答 15% · 跨项目 15% | 16 |
| **preference_memory** | C：个人工作习惯与偏好记忆 | 召回 25% · 抗干扰 15% · 矛盾更新 15% · 效能 15% · 拒答 15% · 跨项目 15% | 13 |
| **knowledge_health** | D：团队知识断层与遗忘预警 | 召回 22% · 抗干扰 22% · 矛盾更新 22% · 长时序 22% · 拒答 11% | 9 |
| **总计** | | | **49** |

### 测试类型说明

| 测试类型 | 比赛要求 | 说明 |
|---------|---------|------|
| `retrieval_recall` | — | 基础记忆召回能力，含事件链式多轮决策提取 |
| `anti_interference` | ⭐ 比赛强制 | 大量无关/高相似信息干扰下仍能召回关键记忆 |
| `contradiction_update` | ⭐ 比赛强制 | 新旧信息冲突时区分历史值与当前有效值 |
| `efficiency` | ⭐ 比赛强制 | 使用记忆后减少操作成本（字符/步骤节省率） |
| `long_term_retention` | — | 跨季度/跨年的记忆保持能力 |
| `abstention` | — | 无相关记忆时正确拒答，不编造答案 |
| `cross_project` | — | 多项目场景下的记忆隔离，防止跨项目泄漏 |

> ⭐ 比赛文档明确要求参赛队伍至少包含**抗干扰测试、矛盾更新测试、效能指标验证**三类测试。  
> command_memory 方向不含 contradiction_update 和 abstention，因为 CLI 命令是统计规律而非事实声明。

---

## 快速开始

### 验证数据格式

```bash
cd benchmark
python scripts/validate_schema.py
```

本目录只保留当前项目评测所需的 benchmark 数据、schema、指标说明和格式校验脚本。实际评测运行器应接入本项目的 Memory Engine 后再实现；原始生成脚本、mock runner 和生成过程文档未复制进来。

---

## 文件结构

```
benchmark/
├── README.md                          # 本文件
├── schema.json                        # 数据格式 JSON Schema v3
├── datasets/                          # 4 个方向 benchmark（JSONL格式）
│   ├── command_memory.jsonl           # 方向 A：CLI 命令记忆（11条）
│   ├── decision_memory.jsonl          # 方向 B：飞书决策记忆（16条）
│   ├── preference_memory.jsonl        # 方向 C：个人偏好记忆（13条）
│   └── knowledge_health.jsonl         # 方向 D：团队知识健康（9条）
├── scripts/
│   └── validate_schema.py             # 数据格式验证工具（含语义校验）
└── docs/
    ├── adapter_mapping.md             # 与 Memory Engine 适配说明
    ├── metrics_definition.md          # 指标体系定义
    └── benchmark_report_template.md   # 报告模板（填写实际数字后提交）
```

---

## 数据格式

每行一个 JSON 对象（JSONL）。核心字段：

```json
{
  "case_id": "dec_contra_001",
  "category": "decision_memory",
  "test_type": "contradiction_update",
  "scenario": "决策方案变更",
  "difficulty": "medium",
  "time_span_days": 21,
  "input_events": [
    {
      "event_id": "e1",
      "timestamp": "2026-04-01T10:00:00",
      "source": "feishu_group",
      "speaker": "技术负责人",
      "content": "缓存层我们决定用Redis。",
      "context": { "project": "LarkMemory" }
    }
  ],
  "query": "我们的缓存层最终用什么方案？",
  "expected": {
    "should_retrieve": true,
    "current_value": "Memcached",
    "inactive_values": ["Redis"],
    "forbidden_active_values": ["Redis"],
    "allow_historical_mention": true,
    "answer_keywords": ["Memcached", "内存占用过高"],
    "evidence_event_ids": ["e2"],
    "superseded_event_ids": ["e1"]
  },
  "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
}
```

**双层判分机制**：
- **answer_correct**：答案文本是否正确（基于 answer_keywords、current_value 等）
- **evidence_correct**：证据来源是否正确（基于 evidence_event_ids）

**关键字段说明**：

| 字段 | 说明 |
|------|------|
| `category` | 所属方向（command_memory / decision_memory / preference_memory / knowledge_health） |
| `test_type` | 测试类型（retrieval_recall / anti_interference / contradiction_update / efficiency / long_term_retention / abstention / cross_project） |
| `time_span_days` | 事件时间跨度（天），用于量化长时序记忆难度 |
| `difficulty` | easy（≤7天）/ medium（8~90天）/ hard（>90天） |
| `evidence_event_ids` | 证据来源事件 ID（必填，用于双层判分） |
| `current_value` / `inactive_values` / `forbidden_active_values` | 矛盾更新的精细判分 |
| `allow_historical_mention` | 是否允许以历史叙述方式提及旧值 |
| `abstention_keywords` / `hallucination_triggers` | 拒答测试的判分依据 |

> **难度分级调研依据**：
> - **easy ≤7 天**：同一迭代内的工作记忆窗口，对应 LOCOMO 单 session 内记忆范围
> - **medium 8~90 天**：跨迭代/跨月，需要跨会话检索，对应 LongMemEvalS (~50 sessions) 的跨会话推理
> - **hard >90 天**：跨季度/跨年，测试真正的"长时序"记忆，学术界（Agent Memory Survey 2026）明确指出这是"尚未解决"的挑战

完整字段定义见 [`schema.json`](schema.json)。

---

## 评分标准

```
总分 = Σ (方向得分 × 权重) × 100

方向权重：
  command_memory:     15%（比赛方向 A）
  decision_memory:    30%（比赛方向 B，核心场景）
  preference_memory:  25%（比赛方向 C）
  knowledge_health:   30%（比赛方向 D）

评级：
  优秀：≥ 85 分
  良好：70~85 分
  待改进：< 70 分
```

---

## 理论依据

本 benchmark 设计参考了以下公开评测基准：

- **LONGMEMEVAL** (ICLR 2025, arXiv:2410.10813) — 长时序记忆评测、Recall@k 指标设计、拒答能力
- **LOCOMO** (ACL Findings 2024, arXiv:2402.17753) — 对抗性测试、Temporal Event Graph、多跳推理
- **MemBench** (ACL Findings 2025, arXiv:2506.21605) — 事实/反思双层次 × 参与/观察双场景 × 效率指标
- **Memory for Autonomous LLM Agents** (Survey, 2026, arXiv:2603.07670) — Agent 记忆机制与评测综述

指标口径详见 [`docs/metrics_definition.md`](docs/metrics_definition.md)，Memory Engine 适配参考 [`docs/adapter_mapping.md`](docs/adapter_mapping.md)。

---

## 版本规划

| 版本 | 内容 | 状态 |
|------|------|------|
| v0.1 | 方案文档 + schema + 8 类 mini benchmark（40条） | ✅ 已归档 |
| v0.2 | 重构为 4 方向 × 5 测试类型结构（40条），难度分级校准 | ✅ 已归档 |
| v1.0 | 7 测试类型 + 双层判分 + 精细矛盾更新 + 拒答 + 跨项目 + 噪声升级（49条） | ✅ **当前** |

