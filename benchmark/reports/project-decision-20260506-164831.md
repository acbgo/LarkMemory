# LarkMemory Benchmark 评测报告

**Run ID**: `project-decision-20260506-164831`
**Suite**: decision_memory
**耗时**: 2189.12s

## 总体结果

| 指标 | 值 |
|------|-----|
| 总分 | **83.6** / 100 |
| 评级 | **良好** |
| 总用例 | 40 |
| 通过 | 27 |
| 失败 | 13 |
| 错误 | 0 |
| 通过率 | 67.5% |

## 按测试类型

| 测试类型 | 用例数 | 通过 | 通过率 | 得分 |
|---------|--------|------|--------|------|
| 基础召回 (retrieval_recall) | 12 | 11 | 91.7% | 95.7 |
| 抗干扰 (anti_interference) | 5 | 3 | 60.0% | 75.0 |
| 矛盾更新 (contradiction_update) | 6 | 4 | 66.7% | 88.9 |
| 效能验证 (efficiency) | 3 | 2 | 66.7% | 85.7 |
| 长时序记忆 (long_term_retention) | 5 | 2 | 40.0% | 70.5 |
| 拒答/防幻觉 (abstention) | 5 | 1 | 20.0% | 50.0 |
| 跨项目隔离 (cross_project) | 4 | 4 | 100.0% | 100.0 |

## 按比赛方向

| 方向 | 权重 | 用例数 | 通过 | 得分 | 加权贡献 |
|------|------|--------|------|------|---------|
| B: 飞书决策记忆 | 0.3 | 40 | 27 | 83.6 | 25.1 |

## 用例详情

| case_id | 方向 | 测试类型 | 难度 | 结果 | 指标详情 |
|---------|------|---------|------|------|---------|
| dec_ret_001 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, rejected_option_match=1.00✓, evidence_match=1.00✓ |
| dec_ret_002 | decision_memory | retrieval_recall | easy | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓, evidence_match=1.00✓ |
| dec_ret_003 | decision_memory | retrieval_recall | medium | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓, decision_match=1.00✓, reason_match=1.00✓ |
| dec_ret_004 | decision_memory | retrieval_recall | medium | ❌ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=0.00✗, evidence_match=0.00✗ |
| dec_ret_005 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_006 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_007 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_008 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_009 | decision_memory | retrieval_recall | medium | ✅ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_010 | decision_memory | retrieval_recall | medium | ✅ | decision_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_011 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| dec_ret_012 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, rejected_option_match=1.00✓, recall_at_3=1.00✓, evidence_m |
| dec_anti_001 | decision_memory | anti_interference | medium | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗, noise_robustness=0.00✗, evidence_match=0.00✗ |
| dec_anti_002 | decision_memory | anti_interference | hard | ❌ | recall_at_3=1.00✓, keyword_match=1.00✓, noise_robustness=1.00✓, old_value_suppression=0.00✗ |
| dec_anti_003 | decision_memory | anti_interference | medium | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓, noise_robustness=1.00✓, evidence_match=1.00✓ |
| dec_anti_004 | decision_memory | anti_interference | medium | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓, noise_robustness=1.00✓, evidence_match=1.00✓ |
| dec_anti_005 | decision_memory | anti_interference | medium | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓, noise_robustness=1.00✓, evidence_match=1.00✓ |
| dec_contra_001 | decision_memory | contradiction_update | medium | ✅ | latest_value_accuracy=1.00✓, old_value_suppression=1.00✓, evidence_match=1.00✓ |
| dec_contra_002 | decision_memory | contradiction_update | hard | ❌ | latest_value_accuracy=1.00✓, old_value_suppression=0.00✗, evidence_match=1.00✓ |
| dec_contra_003 | decision_memory | contradiction_update | hard | ✅ | latest_value_accuracy=1.00✓, old_value_suppression=1.00✓, evidence_match=1.00✓ |
| dec_contra_004 | decision_memory | contradiction_update | medium | ❌ | latest_value_accuracy=1.00✓, old_value_suppression=0.00✗, evidence_match=1.00✓ |
| dec_contra_005 | decision_memory | contradiction_update | medium | ✅ | latest_value_accuracy=1.00✓, old_value_suppression=1.00✓, evidence_match=1.00✓ |
| dec_contra_006 | decision_memory | contradiction_update | hard | ✅ | latest_value_accuracy=1.00✓, old_value_suppression=1.00✓, evidence_match=1.00✓ |
| dec_eff_002 | decision_memory | efficiency | easy | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓ |
| dec_eff_001 | decision_memory | efficiency | medium | ❌ | recall_at_3=1.00✓, char_saving_rate=0.00✗ |
| dec_eff_003 | decision_memory | efficiency | medium | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓, step_saving_rate=1.00✓ |
| dec_long_001 | decision_memory | long_term_retention | hard | ✅ | recall_at_3=1.00✓, long_term_recall=1.00✓, keyword_match=1.00✓, evidence_match=1.00✓ |
| dec_long_002 | decision_memory | long_term_retention | hard | ✅ | recall_at_3=1.00✓, long_term_recall=1.00✓, keyword_match=1.00✓, evidence_match=1.00✓ |
| dec_long_003 | decision_memory | long_term_retention | hard | ❌ | recall_at_3=1.00✓, long_term_recall=1.00✓, keyword_match=0.50✗, evidence_match=1.00✓ |
| dec_long_004 | decision_memory | long_term_retention | hard | ❌ | recall_at_3=1.00✓, long_term_recall=1.00✓, latest_value_accuracy=1.00✓, old_value_suppression=0.00✗, |
| dec_long_005 | decision_memory | long_term_retention | hard | ❌ | recall_at_3=0.00✗, long_term_recall=0.00✗, latest_value_accuracy=0.00✗, old_value_suppression=0.00✗, |
| dec_abs_001 | decision_memory | abstention | medium | ❌ | abstention_accuracy=0.00✗, hallucination_rate=1.00✓ |
| dec_abs_002 | decision_memory | abstention | hard | ❌ | abstention_accuracy=0.00✗, hallucination_rate=1.00✓, noise_robustness=0.00✗ |
| dec_abs_003 | decision_memory | abstention | medium | ❌ | abstention_accuracy=0.00✗, hallucination_rate=1.00✓ |
| dec_abs_004 | decision_memory | abstention | medium | ❌ | abstention_accuracy=0.00✗, hallucination_rate=0.00✗ |
| dec_abs_005 | decision_memory | abstention | medium | ✅ | abstention_accuracy=1.00✓, hallucination_rate=1.00✓, noise_robustness=1.00✓ |
| dec_xproj_001 | decision_memory | cross_project | medium | ✅ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=1.00✓ |
| dec_xproj_002 | decision_memory | cross_project | hard | ✅ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=1.00✓ |
| dec_xproj_003 | decision_memory | cross_project | hard | ✅ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=1.00✓ |
| dec_xproj_004 | decision_memory | cross_project | medium | ✅ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=1.00✓ |