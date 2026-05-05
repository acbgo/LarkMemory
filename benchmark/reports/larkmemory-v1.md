# LarkMemory Benchmark 评测报告

**Run ID**: `larkmemory-v1`
**Suite**: all
**耗时**: 4.02s

## 总体结果

| 指标 | 值 |
|------|-----|
| 总分 | **37.5** / 100 |
| 评级 | **待改进** |
| 总用例 | 49 |
| 通过 | 8 |
| 失败 | 41 |
| 错误 | 0 |
| 通过率 | 16.3% |

## 按测试类型

| 测试类型 | 用例数 | 通过 | 通过率 | 得分 |
|---------|--------|------|--------|------|
| 基础召回 (retrieval_recall) | 15 | 3 | 20.0% | 33.3 |
| 抗干扰 (anti_interference) | 8 | 0 | 0.0% | 23.1 |
| 矛盾更新 (contradiction_update) | 7 | 1 | 14.3% | 50.0 |
| 效能验证 (efficiency) | 7 | 0 | 0.0% | 35.7 |
| 长时序记忆 (long_term_retention) | 3 | 1 | 33.3% | 33.3 |
| 拒答/防幻觉 (abstention) | 5 | 3 | 60.0% | 75.0 |
| 跨项目隔离 (cross_project) | 4 | 0 | 0.0% | 50.0 |

## 按比赛方向

| 方向 | 权重 | 用例数 | 通过 | 得分 | 加权贡献 |
|------|------|--------|------|------|---------|
| A: CLI命令记忆 | 0.15 | 11 | 1 | 38.5 | 5.8 |
| B: 飞书决策记忆 | 0.3 | 16 | 4 | 52.9 | 15.9 |
| C: 个人偏好记忆 | 0.25 | 13 | 1 | 27.3 | 6.8 |
| D: 团队知识健康 | 0.3 | 9 | 2 | 30.0 | 9.0 |

## 用例详情

| case_id | 方向 | 测试类型 | 难度 | 结果 | 指标详情 |
|---------|------|---------|------|------|---------|
| cmd_ret_001 | command_memory | retrieval_recall | easy | ❌ | top1_hit=0.00✗, command_exact_match=0.00✗, recall_at_3=0.00✗ |
| cmd_ret_002 | command_memory | retrieval_recall | easy | ❌ | top1_hit=0.00✗, command_exact_match=0.00✗ |
| cmd_ret_003 | command_memory | retrieval_recall | medium | ❌ | top1_hit=0.00✗, recall_at_3=1.00✓ |
| cmd_ret_004 | command_memory | retrieval_recall | medium | ✅ | recall_at_3=1.00✓, keyword_match=1.00✓ |
| cmd_ret_005 | command_memory | retrieval_recall | hard | ❌ | top1_hit=0.00✗, recall_at_3=0.00✗, keyword_match=1.00✓ |
| dec_ret_001 | decision_memory | retrieval_recall | easy | ✅ | decision_match=1.00✓, reason_match=1.00✓, rejected_option_match=1.00✓, evidence_match=1.00✓ |
| dec_ret_002 | decision_memory | retrieval_recall | easy | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗, evidence_match=0.00✗ |
| dec_ret_003 | decision_memory | retrieval_recall | medium | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗, decision_match=0.00✗, reason_match=0.00✗ |
| dec_ret_004 | decision_memory | retrieval_recall | medium | ✅ | decision_match=1.00✓, reason_match=1.00✓, recall_at_3=1.00✓, evidence_match=1.00✓ |
| pref_ret_001 | preference_memory | retrieval_recall | easy | ❌ | preference_match=0.00✗, condition_match=0.00✗ |
| pref_ret_002 | preference_memory | retrieval_recall | medium | ❌ | preference_match=0.00✗, recall_at_3=0.00✗ |
| pref_ret_003 | preference_memory | retrieval_recall | medium | ❌ | preference_match=0.00✗, recall_at_3=0.00✗ |
| pref_ret_004 | preference_memory | retrieval_recall | hard | ❌ | preference_match=0.00✗, keyword_match=0.00✗, recall_at_3=0.00✗ |
| kh_ret_001 | knowledge_health | retrieval_recall | medium | ❌ | latest_value_accuracy=0.00✗, expired_memory_suppression=1.00✓, evidence_match=0.00✗ |
| kh_ret_002 | knowledge_health | retrieval_recall | medium | ❌ | latest_value_accuracy=0.00✗, recall_at_3=0.00✗, expired_memory_suppression=1.00✓ |
| cmd_anti_001 | command_memory | anti_interference | medium | ❌ | top1_hit=0.00✗, noise_robustness=1.00✓, recall_at_3=1.00✓ |
| cmd_anti_002 | command_memory | anti_interference | hard | ❌ | top1_hit=0.00✗, noise_robustness=1.00✓ |
| dec_anti_001 | decision_memory | anti_interference | medium | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗, noise_robustness=0.00✗, evidence_match=0.00✗ |
| dec_anti_002 | decision_memory | anti_interference | hard | ❌ | recall_at_3=1.00✓, keyword_match=1.00✓, noise_robustness=1.00✓, old_value_suppression=0.00✗ |
| pref_anti_001 | preference_memory | anti_interference | medium | ❌ | recall_at_3=0.00✗, preference_match=0.00✗, noise_robustness=0.00✗ |
| pref_anti_002 | preference_memory | anti_interference | hard | ❌ | preference_match=0.00✗, noise_robustness=0.00✗, recall_at_3=0.00✗ |
| kh_anti_001 | knowledge_health | anti_interference | medium | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗, noise_robustness=0.00✗, evidence_match=0.00✗ |
| kh_anti_002 | knowledge_health | anti_interference | hard | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗, noise_robustness=0.00✗ |
| dec_contra_001 | decision_memory | contradiction_update | medium | ❌ | latest_value_accuracy=1.00✓, old_value_suppression=0.00✗, evidence_match=0.00✗ |
| dec_contra_002 | decision_memory | contradiction_update | hard | ❌ | latest_value_accuracy=0.00✗, old_value_suppression=1.00✓, evidence_match=0.00✗ |
| dec_contra_003 | decision_memory | contradiction_update | hard | ❌ | latest_value_accuracy=1.00✓, old_value_suppression=1.00✓, evidence_match=0.00✗ |
| pref_contra_001 | preference_memory | contradiction_update | medium | ❌ | latest_value_accuracy=0.00✗, old_value_suppression=1.00✓, evidence_match=0.00✗ |
| pref_contra_002 | preference_memory | contradiction_update | hard | ❌ | latest_value_accuracy=0.00✗, old_value_suppression=1.00✓, preference_match=0.00✗ |
| kh_contra_001 | knowledge_health | contradiction_update | medium | ❌ | latest_value_accuracy=0.00✗, old_value_suppression=1.00✓, expired_memory_suppression=1.00✓, evidence |
| kh_contra_002 | knowledge_health | contradiction_update | hard | ✅ | latest_value_accuracy=1.00✓, old_value_suppression=1.00✓, evidence_match=1.00✓ |
| cmd_eff_001 | command_memory | efficiency | easy | ❌ | top1_hit=0.00✗, char_saving_rate=1.00✓ |
| cmd_eff_002 | command_memory | efficiency | medium | ❌ | top1_hit=0.00✗, char_saving_rate=1.00✓ |
| cmd_eff_003 | command_memory | efficiency | hard | ❌ | top1_hit=0.00✗, char_saving_rate=1.00✓ |
| dec_eff_002 | decision_memory | efficiency | easy | ❌ | recall_at_3=0.00✗, keyword_match=0.00✗ |
| dec_eff_001 | decision_memory | efficiency | medium | ❌ | recall_at_3=1.00✓, char_saving_rate=0.00✗ |
| pref_eff_001 | preference_memory | efficiency | easy | ❌ | preference_match=0.00✗, char_saving_rate=0.00✗ |
| pref_eff_002 | preference_memory | efficiency | medium | ❌ | preference_match=0.00✗, step_saving_rate=1.00✓ |
| dec_long_001 | decision_memory | long_term_retention | hard | ✅ | recall_at_3=1.00✓, long_term_recall=1.00✓, keyword_match=1.00✓, evidence_match=1.00✓ |
| kh_long_001 | knowledge_health | long_term_retention | hard | ❌ | recall_at_3=0.00✗, long_term_recall=0.00✗, keyword_match=0.00✗, evidence_match=0.00✗ |
| kh_long_002 | knowledge_health | long_term_retention | hard | ❌ | recall_at_3=0.00✗, long_term_recall=0.00✗, keyword_match=0.00✗, evidence_match=0.00✗ |
| dec_abs_001 | decision_memory | abstention | medium | ✅ | abstention_accuracy=1.00✓, hallucination_rate=1.00✓ |
| dec_abs_002 | decision_memory | abstention | hard | ❌ | abstention_accuracy=0.00✗, hallucination_rate=1.00✓, noise_robustness=0.00✗ |
| pref_abs_001 | preference_memory | abstention | medium | ✅ | abstention_accuracy=1.00✓, hallucination_rate=1.00✓ |
| pref_abs_002 | preference_memory | abstention | hard | ❌ | abstention_accuracy=1.00✓, hallucination_rate=1.00✓, noise_robustness=0.00✗ |
| kh_abs_001 | knowledge_health | abstention | medium | ✅ | abstention_accuracy=1.00✓, hallucination_rate=1.00✓ |
| cmd_xproj_001 | command_memory | cross_project | medium | ❌ | scope_accuracy=0.00✗, cross_project_leakage_rate=0.00✗, evidence_match=0.00✗ |
| dec_xproj_001 | decision_memory | cross_project | medium | ❌ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=0.00✗ |
| dec_xproj_002 | decision_memory | cross_project | hard | ❌ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=0.00✗ |
| pref_xproj_001 | preference_memory | cross_project | medium | ❌ | scope_accuracy=1.00✓, cross_project_leakage_rate=1.00✓, evidence_match=0.00✗ |