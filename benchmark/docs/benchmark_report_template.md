# LarkMemory Benchmark 评测报告

> **评测日期**: YYYY-MM-DD  
> **评测版本**: v1.0  
> **Memory Engine 版本**: vX.X.X  
> **评测环境**: [本地/服务器配置]

---

## 1. 总分

| 指标 | 得分 |
|------|------|
| **总分** | **X.XX / 100** |
| 评级 | 优秀 / 良好 / 待改进 |

## 2. 各方向得分

| 方向 Benchmark | 权重 | 得分 | 等级 |
|---------------|------|------|------|
| command_memory（方向 A） | 15% | X.XX | |
| decision_memory（方向 B） | 30% | X.XX | |
| preference_memory（方向 C） | 25% | X.XX | |
| knowledge_health（方向 D） | 30% | X.XX | |

## 3. 各测试类型得分

| 测试类型 | 比赛要求 | 总体得分 | 涉及方向 |
|---------|---------|---------|---------|
| retrieval_recall | — | X.XX | A, B, C, D |
| ⭐ anti_interference | 比赛强制 | X.XX | A, B, C, D |
| ⭐ contradiction_update | 比赛强制 | X.XX | B, C, D |
| ⭐ efficiency | 比赛强制 | X.XX | A, B, C |
| long_term_retention | — | X.XX | B, D |
| cross_project | — | X.XX | A, B, C |
| abstention | — | X.XX | B, C, D |

> ⭐ 比赛文档明确要求至少包含抗干扰、矛盾更新、效能三类测试。
> cross_project 和 abstention 为企业级记忆系统的差异化评测维度。

## 4. 分方向详细结果

### 4.1 command_memory（方向 A：CLI 命令记忆）

| 测试类型 | 条数 | 通过 | 得分 |
|---------|------|------|------|
| retrieval_recall | X | X | X.XX |
| efficiency | X | X | X.XX |
| anti_interference | X | X | X.XX |
| cross_project | X | X | X.XX |
| **小计** | **X** | **X** | **X.XX** |

### 4.2 decision_memory（方向 B：飞书决策记忆）

| 测试类型 | 条数 | 通过 | 得分 |
|---------|------|------|------|
| retrieval_recall | X | X | X.XX |
| anti_interference | X | X | X.XX |
| contradiction_update | X | X | X.XX |
| efficiency | X | X | X.XX |
| long_term_retention | X | X | X.XX |
| cross_project | X | X | X.XX |
| abstention | X | X | X.XX |
| **小计** | **X** | **X** | **X.XX** |

### 4.3 preference_memory（方向 C：个人偏好记忆）

| 测试类型 | 条数 | 通过 | 得分 |
|---------|------|------|------|
| retrieval_recall | X | X | X.XX |
| anti_interference | X | X | X.XX |
| contradiction_update | X | X | X.XX |
| efficiency | X | X | X.XX |
| cross_project | X | X | X.XX |
| abstention | X | X | X.XX |
| **小计** | **X** | **X** | **X.XX** |

### 4.4 knowledge_health（方向 D：团队知识健康）

| 测试类型 | 条数 | 通过 | 得分 |
|---------|------|------|------|
| retrieval_recall | X | X | X.XX |
| anti_interference | X | X | X.XX |
| contradiction_update | X | X | X.XX |
| long_term_retention | X | X | X.XX |
| abstention | X | X | X.XX |
| **小计** | **X** | **X** | **X.XX** |

## 5. 指标详情

| 指标 | 总 case 数 | 通过 | 通过率 |
|------|-----------|------|--------|
| recall_at_3 | X | X | X.X% |
| keyword_match | X | X | X.X% |
| evidence_match | X | X | X.X% |
| noise_robustness | X | X | X.X% |
| latest_value_accuracy | X | X | X.X% |
| old_value_suppression | X | X | X.X% |
| char_saving_rate | X | X | X.X% |
| long_term_recall | X | X | X.X% |
| abstention_accuracy | X | X | X.X% |
| hallucination_rate | X | X | X.X% |
| scope_accuracy | X | X | X.X% |
| cross_project_leakage_rate | X | X | X.X% |

## 6. 失败 case 分析

| case_id | 方向 | 测试类型 | 失败指标 | 原因分析 |
|---------|------|---------|---------|---------|
| | | | | |

## 7. 改进建议

1. ...
2. ...

---

*本报告由 `python scripts/run_benchmark.py --all --output reports/eval_YYYYMMDD.json` 自动生成。*
