#!/usr/bin/env python3
"""
Generate 24 new decision_memory benchmark cases adapted from MemScope D direction,
appending to the existing 16 cases to reach 40 total.

MemScope reference: eval/datasets/decision_memory.json (30 cases)
Target: 16 existing + 24 new = 40 cases for LarkMemory D direction.
"""

import json
import os

NEW_CASES = [
    # ============================================================
    # retrieval_recall (8 new: dec_ret_005 ~ dec_ret_012)
    # Adapted from MemScope dec_001~dec_010, dec_011~dec_015
    # ============================================================

    {
        "case_id": "dec_ret_005",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "中文决策动词识别-定下来",
        "difficulty": "easy",
        "time_span_days": 1,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "数据库选型讨论了好几天了，MySQL和PostgreSQL都可以，大家怎么看？",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-01T10:01:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "MySQL适合简单场景，PostgreSQL对JSON支持更好。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e3",
                "timestamp": "2026-04-01T10:02:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "好的，数据库就定下来用PostgreSQL吧，JSON支持对我们很重要。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "我们数据库最终选了什么？为什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["PostgreSQL", "JSON支持"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["decision_match", "reason_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_006",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "中文决策动词识别-敲定",
        "difficulty": "easy",
        "time_span_days": 1,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-02T14:00:00",
                "source": "feishu_group",
                "speaker": "项目经理",
                "content": "方案A和方案B的对比报告出来了，A的成本更低但周期长，B快但贵。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-02T14:05:00",
                "source": "feishu_group",
                "speaker": "项目经理",
                "content": "综合考虑，方案A就敲定了，下周开始执行。虽然周期长但ROI更高。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "最终执行哪个方案？什么时候开始？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["方案A", "下周"],
            "forbidden_active_values": ["方案B"],
            "evidence_event_ids": ["e2"]
        },
        "metrics": ["decision_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_007",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "中文决策动词识别-确认",
        "difficulty": "easy",
        "time_span_days": 1,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-03T09:00:00",
                "source": "feishu_group",
                "speaker": "前端负责人",
                "content": "移动端技术栈大家讨论一下，Flutter还是React Native？",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-03T09:01:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "Flutter性能更好，但RN生态更成熟，团队已有JS经验。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e3",
                "timestamp": "2026-04-03T09:10:00",
                "source": "feishu_group",
                "speaker": "前端负责人",
                "content": "确认采用React Native作为移动端方案，主要是团队技术栈匹配。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "移动端用的什么框架？为什么选它？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["React Native", "技术栈匹配"],
            "forbidden_active_values": ["Flutter"],
            "evidence_event_ids": ["e3"]
        },
        "metrics": ["decision_match", "reason_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_008",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "中文决策动词识别-选定含精确版本号",
        "difficulty": "easy",
        "time_span_days": 1,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-05T15:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "Python版本需要统一，3.9还是3.11？",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-05T15:03:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "选定Python 3.11作为项目标准版本，性能提升明显且兼容性好。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "项目标准Python版本是多少？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Python 3.11", "性能提升"],
            "forbidden_active_values": ["Python 3.9"],
            "evidence_event_ids": ["e2"]
        },
        "metrics": ["decision_match", "reason_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_009",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "英文决策动词识别-decided",
        "difficulty": "medium",
        "time_span_days": 14,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-06T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps Lead",
                "content": "We need to choose an orchestration platform: K8s, Docker Swarm, or Nomad.",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "Docker Swarm配置比较简单，但功能有限。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-14T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "K8s学习曲线陡峭，要不要再考虑一下？"
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-20T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps Lead",
                "content": "After evaluating all options, we decided to go with Kubernetes for orchestration. The ecosystem and community support are unmatched.",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "What orchestration platform did we choose and why?",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Kubernetes", "ecosystem", "community"],
            "forbidden_active_values": ["Docker Swarm", "Nomad"],
            "evidence_event_ids": ["e2"]
        },
        "metrics": ["decision_match", "reason_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_010",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "英文决策动词识别-finalized",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-20T10:00:00",
                "source": "feishu_group",
                "speaker": "API Architect",
                "content": "API draft v1 was rejected due to inconsistent naming conventions.",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "API Architect",
                "content": "API draft v2 reviewed and feedback incorporated.",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-08T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "v2的接口定义比v1清晰多了。"
            },
            {
                "event_id": "e3",
                "timestamp": "2026-04-10T10:00:00",
                "source": "feishu_group",
                "speaker": "API Architect",
                "content": "The API contract has been finalized with v2 endpoints. All teams should start integration.",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "What API version is finalized and what was rejected before?",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["v2", "v1", "finalized"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["decision_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_011",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "决策理由提取-因为引导因果关系",
        "difficulty": "medium",
        "time_span_days": 7,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-11T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "最终采用MongoDB作为主数据库，因为文档模型匹配我们的数据结构，而且水平扩展能力好。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-13T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "MongoDB的查询语法需要学习一下。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-16T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "PostgreSQL也能存JSON，要不要重新考虑？"
            }
        ],
        "query": "为什么选择MongoDB作为主数据库？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["MongoDB", "文档模型", "水平扩展"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["decision_match", "reason_match", "recall_at_3", "evidence_match"]
    },

    {
        "case_id": "dec_ret_012",
        "category": "decision_memory",
        "test_type": "retrieval_recall",
        "scenario": "否决决策提取-放弃X改用Y",
        "difficulty": "medium",
        "time_span_days": 7,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-15T09:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "API方案最终放弃了GraphQL，改用REST API。原因是我们团队对GraphQL经验不足，而且REST的工具链更成熟。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-17T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "REST API的Swagger文档已经生成了。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "GraphQL其实也挺好的，可惜了。"
            }
        ],
        "query": "我们API方案最终用了什么？放弃了什么？为什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["REST API", "GraphQL", "经验不足", "工具链"],
            "forbidden_active_values": ["GraphQL"],
            "allow_historical_mention": True,
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["decision_match", "reason_match", "rejected_option_match", "recall_at_3", "evidence_match"]
    },

    # ============================================================
    # anti_interference (3 new: dec_anti_003 ~ dec_anti_005)
    # Adapted from MemScope dec_021~dec_025 search accuracy concepts
    # ============================================================

    {
        "case_id": "dec_anti_003",
        "category": "decision_memory",
        "test_type": "anti_interference",
        "scenario": "高相似技术选型噪声中召回正确决策",
        "difficulty": "hard",
        "time_span_days": 90,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-15T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "消息队列最终选型确定：使用Redis Stream，因为我们QPS不高且已有Redis，不用引入新组件。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-01-20T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Kafka的吞吐量确实很高，适合大数据场景。"},
            {"event_id": "noise_2", "timestamp": "2026-01-25T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "RabbitMQ的Exchange路由功能很灵活。"},
            {"event_id": "noise_3", "timestamp": "2026-02-01T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Redis Stream的消费组机制够用了。"},
            {"event_id": "noise_4", "timestamp": "2026-02-05T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "如果以后QPS涨了可能要换Kafka。"},
            {"event_id": "noise_5", "timestamp": "2026-02-10T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "你们觉得要不要提前上Kafka？"},
            {"event_id": "noise_6", "timestamp": "2026-02-15T14:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "消息队列选型讨论文档我发了。"},
            {"event_id": "noise_7", "timestamp": "2026-02-20T09:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Kafka的运维成本需要考虑。"},
            {"event_id": "noise_8", "timestamp": "2026-02-25T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Redis Stream的ACK机制够用吗？"},
            {"event_id": "noise_9", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "RabbitMQ的插件体系很强大。"},
            {"event_id": "noise_10", "timestamp": "2026-03-05T11:00:00", "source": "feishu_group", "speaker": "成员D", "content": "有人调研过Pulsar吗？据说也不错。"},
            {"event_id": "noise_11", "timestamp": "2026-03-10T09:00:00", "source": "feishu_group", "speaker": "成员C", "content": "现在Redis Stream跑得挺好的。"},
            {"event_id": "noise_12", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Kafka Streams做实时处理很好用。"},
            {"event_id": "noise_13", "timestamp": "2026-03-20T14:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "下周讨论是否升级消息队列方案。"},
            {"event_id": "noise_14", "timestamp": "2026-03-28T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Alpha项目用的是Kafka，我们也可以考虑。"},
            {"event_id": "noise_15", "timestamp": "2026-04-01T09:00:00", "source": "feishu_group", "speaker": "成员D", "content": "消息队列的监控面板做好了。"},
            {"event_id": "noise_16", "timestamp": "2026-04-05T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Redis 7.0的Stream功能又增强了。"},
            {"event_id": "noise_17", "timestamp": "2026-04-10T11:00:00", "source": "feishu_group", "speaker": "成员A", "content": "轻量级场景Redis Stream确实是最优选择。"},
            {"event_id": "noise_18", "timestamp": "2026-04-13T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Kafka还是行业标准。"}
        ],
        "query": "我们项目中消息队列最初确定用什么方案？为什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Redis Stream", "已有Redis", "不用引入新组件"],
            "forbidden_active_values": ["Kafka"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    {
        "case_id": "dec_anti_004",
        "category": "decision_memory",
        "test_type": "anti_interference",
        "scenario": "多方案讨论后精确召回否决决策",
        "difficulty": "hard",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-02-10T10:00:00",
                "source": "feishu_group",
                "speaker": "技术负责人",
                "content": "综合考虑后，前端不做SSR了。我们SEO需求不强，CSR够用且开发更快。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-12T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Next.js的SSR方案真的很成熟。"},
            {"event_id": "noise_2", "timestamp": "2026-02-18T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Nuxt3支持混合渲染，SSR和CSR都行。"},
            {"event_id": "noise_3", "timestamp": "2026-02-22T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "SSR对SEO确实有帮助，但我们不面向C端。"},
            {"event_id": "noise_4", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "要不要分页面做SSR？需要SEO的页面用SSR。"},
            {"event_id": "noise_5", "timestamp": "2026-03-05T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "CSR的首屏加载需要优化一下。"},
            {"event_id": "noise_6", "timestamp": "2026-03-10T14:00:00", "source": "feishu_group", "speaker": "成员D", "content": "我看到很多内部系统都用CSR，完全够用。"},
            {"event_id": "noise_7", "timestamp": "2026-03-15T09:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "我们的用户主要是内部员工，SEO不重要。"},
            {"event_id": "noise_8", "timestamp": "2026-03-20T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Remix框架的SSR体验做得特别好。"},
            {"event_id": "noise_9", "timestamp": "2026-03-25T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "CSR开发效率确实高，改完直接刷新。"},
            {"event_id": "noise_10", "timestamp": "2026-03-30T11:00:00", "source": "feishu_group", "speaker": "成员B", "content": "我们要不要搞个SSR的技术预研？"},
            {"event_id": "noise_11", "timestamp": "2026-04-05T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Astro框架可以做到部分SSR，挺灵活的。"}
        ],
        "query": "我们前端渲染方案是什么？为什么不用SSR？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["CSR", "SEO需求不强", "开发更快"],
            "forbidden_active_values": ["SSR"],
            "allow_historical_mention": True,
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    {
        "case_id": "dec_anti_005",
        "category": "decision_memory",
        "test_type": "anti_interference",
        "scenario": "中英文混杂环境中精确召回中文决策",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-15T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "最终确定：采用事件驱动架构替代传统的请求-响应模式，因为我们有大量实时协作场景。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-03-16T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "The event-driven approach will require a message broker for sure."},
            {"event_id": "noise_2", "timestamp": "2026-03-18T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Event sourcing pattern is interesting but complex to implement."},
            {"event_id": "noise_3", "timestamp": "2026-03-20T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "CQRS with event-driven can separate read/write paths nicely."},
            {"event_id": "noise_4", "timestamp": "2026-03-22T14:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Eventual consistency is something we need to think about carefully."},
            {"event_id": "noise_5", "timestamp": "2026-03-25T09:00:00", "source": "feishu_group", "speaker": "成员D", "content": "请求-响应模式虽然简单，但扩展性确实不如事件驱动。"},
            {"event_id": "noise_6", "timestamp": "2026-03-28T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "The event bus implementation details need more discussion."},
            {"event_id": "noise_7", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "Architecture review is scheduled for next Monday."},
            {"event_id": "noise_8", "timestamp": "2026-04-05T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Saga pattern with event-driven is great for distributed transactions."},
            {"event_id": "noise_9", "timestamp": "2026-04-08T11:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Dead letter queue handling is a must for event-driven systems."},
            {"event_id": "noise_10", "timestamp": "2026-04-12T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "Event schema versioning will be important going forward."}
        ],
        "query": "我们的系统架构模式是什么？为什么选这个？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["事件驱动", "实时协作"],
            "forbidden_active_values": ["请求-响应"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    # ============================================================
    # contradiction_update (3 new: dec_contra_004 ~ dec_contra_006)
    # Adapted from MemScope dec_018, dec_019, dec_020
    # ============================================================

    {
        "case_id": "dec_contra_004",
        "category": "decision_memory",
        "test_type": "contradiction_update",
        "scenario": "许可证变更导致决策推翻重定",
        "difficulty": "hard",
        "time_span_days": 90,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-18T10:00:00",
                "source": "feishu_group",
                "speaker": "技术负责人",
                "content": "日志收集方案就定ELK了，Elasticsearch+Logstash+Kibana成熟稳定。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-02-01T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "ELK集群已经开始搭建了。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-02-15T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "Kibana的dashboard配置挺方便的。"
            },
            {
                "event_id": "e2",
                "timestamp": "2026-03-01T14:00:00",
                "source": "feishu_group",
                "speaker": "法务",
                "content": "Elasticsearch许可证从Apache变更为SSPL，需要评估合规风险。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-03-05T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "SSPL许可证有什么限制？"
            },
            {
                "event_id": "noise_4",
                "timestamp": "2026-03-10T10:00:00",
                "source": "feishu_group",
                "speaker": "法务",
                "content": "SSPL要求如果提供Elasticsearch作为服务，需要开源整个服务代码。这对我们不适用但需要评估。"
            },
            {
                "event_id": "noise_5",
                "timestamp": "2026-03-15T14:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "有没有ES的开源替代方案？"
            },
            {
                "event_id": "noise_6",
                "timestamp": "2026-03-20T09:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "Loki是Grafana出的，专门做日志聚合，Apache 2.0许可证。"
            },
            {
                "event_id": "e3",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "技术负责人",
                "content": "鉴于ES许可证风险，决定改用Loki+Grafana方案替代ELK，开源且轻量。ELK集群搭建工作暂停。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "我们日志收集最终用什么方案？之前用的是什么？为什么换了？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "current_value": "Loki+Grafana",
            "inactive_values": ["ELK"],
            "forbidden_active_values": ["ELK", "Elasticsearch"],
            "allow_historical_mention": True,
            "answer_keywords": ["Loki", "Grafana", "许可证", "SSPL"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    {
        "case_id": "dec_contra_005",
        "category": "decision_memory",
        "test_type": "contradiction_update",
        "scenario": "隐式行动暗示决策变更",
        "difficulty": "hard",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-02-01T10:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "缓存方案还是Redis和Memcached二选一。先按Redis来做吧。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-02-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "Redis集群配置文档我更新了。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-02-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "Redis的sentinel模式够用了。"
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-03-01T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "Redis内存占用有点高，有没有优化方案？"
            },
            {
                "event_id": "noise_4",
                "timestamp": "2026-03-10T14:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "Memcached的内存管理效率更高一些。"
            },
            {
                "event_id": "noise_5",
                "timestamp": "2026-03-15T11:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "要不要做个Redis和Memcached的性能对比？"
            },
            {
                "event_id": "noise_6",
                "timestamp": "2026-03-20T09:00:00",
                "source": "feishu_group",
                "speaker": "产品经理",
                "content": "缓存层性能需要优化，最近响应时间有点慢。"
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "不纠结了，我已经把Memcached配置加上了，内存效率确实好很多。Redis先留着做队列。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "我们缓存层现在用什么？之前考虑过什么方案？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "current_value": "Memcached",
            "inactive_values": ["Redis"],
            "forbidden_active_values": ["Redis"],
            "allow_historical_mention": True,
            "answer_keywords": ["Memcached", "内存效率"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    {
        "case_id": "dec_contra_006",
        "category": "decision_memory",
        "test_type": "contradiction_update",
        "scenario": "条件决策随阈值触发而更新",
        "difficulty": "hard",
        "time_span_days": 180,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-11-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "消息队列方案分两个阶段：当前用户量少用Redis Stream，如果DAU超过50万就升级到Kafka。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2025-11-15T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "Redis Stream目前运行稳定。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2025-12-01T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "用户量在增长，上个月DAU到了30万。"
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-01-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "DAU已经45万了，Redis Stream偶尔有延迟。"
            },
            {
                "event_id": "noise_4",
                "timestamp": "2026-02-01T14:00:00",
                "source": "feishu_group",
                "speaker": "产品经理",
                "content": "Q1运营活动预计会带来一波增长。"
            },
            {
                "event_id": "noise_5",
                "timestamp": "2026-02-15T09:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "要不要提前开始准备Kafka迁移？"
            },
            {
                "event_id": "noise_6",
                "timestamp": "2026-02-28T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "等DAU确过50万再启动迁移，现在先做好预案。"
            },
            {
                "event_id": "e2",
                "timestamp": "2026-03-15T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "DAU已突破55万，按之前约定启动Kafka迁移。Redis Stream方案将在迁移完成后退役。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "现在消息队列用的什么方案？之前用的什么？为什么换了？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "current_value": "Kafka",
            "inactive_values": ["Redis Stream"],
            "forbidden_active_values": ["Redis Stream"],
            "allow_historical_mention": True,
            "answer_keywords": ["Kafka", "DAU", "55万", "50万"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    # ============================================================
    # cross_project (2 new: dec_xproj_003 ~ dec_xproj_004)
    # Adapted from MemScope dec_021~dec_025 search concepts
    # ============================================================

    {
        "case_id": "dec_xproj_003",
        "category": "decision_memory",
        "test_type": "cross_project",
        "scenario": "三项目不同数据库选型精确隔离",
        "difficulty": "hard",
        "time_span_days": 180,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-10-15T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "Alpha项目使用PostgreSQL作为主数据库，原因是需要复杂事务支持和JSON字段。",
                "context": {"project": "Alpha"}
            },
            {
                "event_id": "e2",
                "timestamp": "2025-11-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "Beta项目使用MongoDB作为主数据库，文档模型更匹配业务数据结构。",
                "context": {"project": "Beta"}
            },
            {
                "event_id": "e3",
                "timestamp": "2025-12-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "Gamma项目使用MySQL，因为成本最低且团队最熟悉。",
                "context": {"project": "Gamma"}
            },
            {"event_id": "noise_1", "timestamp": "2026-01-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "PostgreSQL的查询性能不错。", "context": {"project": "Alpha"}},
            {"event_id": "noise_2", "timestamp": "2026-01-25T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "MongoDB聚合管道好强大。"},
            {"event_id": "noise_3", "timestamp": "2026-02-05T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "MySQL的InnoDB引擎调优有推荐的参数吗？"},
            {"event_id": "noise_4", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Alpha的数据库备份完成了。", "context": {"project": "Alpha"}},
            {"event_id": "noise_5", "timestamp": "2026-02-25T14:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Beta的文档结构又要改了。", "context": {"project": "Beta"}},
            {"event_id": "noise_6", "timestamp": "2026-03-05T09:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "三个项目的数据库选型汇总发群里了。"},
            {"event_id": "noise_7", "timestamp": "2026-03-10T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Gamma的MySQL版本有点老。"},
            {"event_id": "noise_8", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "MongoDB适合灵活schema，PG适合复杂查询。"},
            {"event_id": "noise_9", "timestamp": "2026-03-20T11:00:00", "source": "feishu_group", "speaker": "成员D", "content": "Alpha的数据库迁移方案我看了。", "context": {"project": "Alpha"}},
            {"event_id": "noise_10", "timestamp": "2026-03-28T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Beta项目的数据模型评审下周。", "context": {"project": "Beta"}},
            {"event_id": "noise_11", "timestamp": "2026-04-05T09:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Gamma用MySQL挺稳的。"},
            {"event_id": "noise_12", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "PostgreSQL 17的新特性有人在关注吗？"}
        ],
        "query": "Beta项目当前使用什么数据库？选型理由是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Beta", "MongoDB", "文档模型"],
            "forbidden_active_values": ["PostgreSQL", "MySQL"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1", "e3"]
        },
        "metrics": ["scope_accuracy", "cross_project_leakage_rate", "evidence_match"]
    },

    {
        "case_id": "dec_xproj_004",
        "category": "decision_memory",
        "test_type": "cross_project",
        "scenario": "多项目部署策略时间线隔离",
        "difficulty": "medium",
        "time_span_days": 90,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-10T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "Alpha项目使用蓝绿部署策略，可以减少停机时间。",
                "context": {"project": "Alpha"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-02-15T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "Beta项目使用滚动更新策略，因为需要保持服务不中断。",
                "context": {"project": "Beta"}
            },
            {
                "event_id": "e3",
                "timestamp": "2026-03-20T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "Gamma项目使用金丝雀发布，先10%流量验证再全量。",
                "context": {"project": "Gamma"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "蓝绿部署需要双倍资源，成本有点高。"},
            {"event_id": "noise_2", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "滚动更新配合健康检查很稳。"},
            {"event_id": "noise_3", "timestamp": "2026-03-25T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "金丝雀发布需要流量路由配置。"},
            {"event_id": "noise_4", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "各项目的发布策略文档更新了。"},
            {"event_id": "noise_5", "timestamp": "2026-04-05T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Alpha的蓝绿切换脚本写好了。", "context": {"project": "Alpha"}},
            {"event_id": "noise_6", "timestamp": "2026-04-08T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Beta的滚动更新有没有回滚机制？", "context": {"project": "Beta"}},
            {"event_id": "noise_7", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "金丝雀10%的比例是否需要调整？"}
        ],
        "query": "Beta项目的部署策略是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Beta", "滚动更新", "服务不中断"],
            "forbidden_active_values": ["蓝绿部署", "金丝雀发布"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1", "e3"]
        },
        "metrics": ["scope_accuracy", "cross_project_leakage_rate", "evidence_match"]
    },

    # ============================================================
    # efficiency (1 new: dec_eff_003)
    # ============================================================

    {
        "case_id": "dec_eff_003",
        "category": "decision_memory",
        "test_type": "efficiency",
        "scenario": "历史技术决策加速新人项目上手",
        "difficulty": "easy",
        "time_span_days": 14,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "技术负责人",
                "content": "新人入职技术栈清单确认：后端用Python 3.11 + FastAPI，数据库用PostgreSQL，缓存用Memcached，消息队列用Redis Stream。IDE统一使用VSCode，配置文件在项目仓库。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-05T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "FastAPI文档生成真方便。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "新来的同事问我环境怎么配。"
            }
        ],
        "query": "新人入职需要了解哪些技术栈和环境配置？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Python 3.11", "FastAPI", "PostgreSQL", "Memcached", "Redis Stream", "VSCode"],
            "baseline_steps": 5,
            "min_saving_rate": 0.6,
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "step_saving_rate"]
    },

    # ============================================================
    # long_term_retention (4 new: dec_long_002 ~ dec_long_005)
    # Adapted from MemScope dec_026~dec_030
    # ============================================================

    {
        "case_id": "dec_long_002",
        "category": "decision_memory",
        "test_type": "long_term_retention",
        "scenario": "90天前核心服务重写决策跨季度召回",
        "difficulty": "hard",
        "time_span_days": 95,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-30T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "核心服务使用Go语言重写，原Python版本性能瓶颈明显。Go的并发模型和编译特性更适合高并发场景。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Go的goroutine用起来确实顺手。"},
            {"event_id": "noise_2", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Python那边的代码还需要维护吗？"},
            {"event_id": "noise_3", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Go重写进度到60%了。"},
            {"event_id": "noise_4", "timestamp": "2026-03-30T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "新的Go服务QPS提升了3倍。"},
            {"event_id": "noise_5", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "要不要用Rust？据说性能更好。"},
            {"event_id": "noise_6", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "最近Zig语言也很火。"},
            {"event_id": "noise_7", "timestamp": "2026-04-25T14:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "Go重写项目的终验时间定了吗？"},
            {"event_id": "noise_8", "timestamp": "2026-04-28T09:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Go 1.23发布了，新特性不少。"},
            {"event_id": "noise_9", "timestamp": "2026-05-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Python重写为Go是一个正确的决定。"}
        ],
        "query": "核心服务是用什么语言重写的？为什么选它？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["Go", "并发", "高并发"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "dec_long_003",
        "category": "decision_memory",
        "test_type": "long_term_retention",
        "scenario": "部署方案四阶段渐进式演进链路召回",
        "difficulty": "hard",
        "time_span_days": 180,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-11-01T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "从手动部署改为脚本自动化部署，减少人工操作失误。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2025-12-15T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "部署脚本升级为Docker容器化，解决环境一致性问题。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e3",
                "timestamp": "2026-02-01T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "容器化部署迁移到Kubernetes，实现自动扩缩容和服务编排。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e4",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "Kubernetes部署采用Helm Chart管理，统一配置和版本控制。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2025-12-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "脚本部署比手动快多了。"},
            {"event_id": "noise_2", "timestamp": "2026-01-10T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Docker镜像构建有点慢。"},
            {"event_id": "noise_3", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "K8s的YAML文件好复杂。"},
            {"event_id": "noise_4", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "要不要试试Terraform做基础设施管理？"},
            {"event_id": "noise_5", "timestamp": "2026-03-20T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "Helm Chart的模板语法需要适应一下。"},
            {"event_id": "noise_6", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "从手动到Helm，部署效率提升了不止10倍。"},
            {"event_id": "noise_7", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "部署流程演进文档需要更新了。"}
        ],
        "query": "我们的部署方案经历了哪些阶段的演进？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "answer_keywords": ["脚本自动化", "Docker", "Kubernetes", "Helm Chart"],
            "evidence_event_ids": ["e1", "e2", "e3", "e4"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "dec_long_004",
        "category": "decision_memory",
        "test_type": "long_term_retention",
        "scenario": "API方案经历采用-变更-回退的完整变迁",
        "difficulty": "hard",
        "time_span_days": 200,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-10-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "API设计采用REST风格，简单直观，团队都有经验。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-01-05T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "内部服务API改用GraphQL，前端可以灵活查询需要的字段，减少网络请求。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-01-20T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "GraphQL的schema定义需要好好设计。"},
            {"event_id": "noise_2", "timestamp": "2026-02-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "GraphQL的N+1查询问题需要注意。"},
            {"event_id": "noise_3", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "DataLoader可以解决N+1问题。"},
            {"event_id": "noise_4", "timestamp": "2026-03-01T14:00:00", "source": "feishu_group", "speaker": "成员A", "content": "GraphQL的查询复杂度越来越高了。"},
            {"event_id": "noise_5", "timestamp": "2026-03-10T09:00:00", "source": "feishu_group", "speaker": "成员B", "content": "这个GraphQL查询耗了5秒，太慢了。"},
            {"event_id": "noise_6", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "GraphQL缓存不太好做啊。"},
            {"event_id": "noise_7", "timestamp": "2026-03-22T11:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "API响应速度最近下降明显。"},
            {"event_id": "noise_8", "timestamp": "2026-03-28T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "REST虽然啰嗦但可控性强。"},
            {
                "event_id": "e3",
                "timestamp": "2026-04-15T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "GraphQL方案遇到严重性能问题且缓存困难，决定回退到REST API。保留GraphQL仅用于管理后台的数据分析页面。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "我们的API方案经历了哪些变化？当前用的是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "current_value": "REST API",
            "inactive_values": ["GraphQL"],
            "forbidden_active_values": ["GraphQL"],
            "allow_historical_mention": True,
            "answer_keywords": ["REST", "GraphQL", "性能问题", "回退"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1", "e2"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    {
        "case_id": "dec_long_005",
        "category": "decision_memory",
        "test_type": "long_term_retention",
        "scenario": "被覆盖的旧Sprint周期决策仍可历史查询",
        "difficulty": "medium",
        "time_span_days": 120,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-05T10:00:00",
                "source": "feishu_group",
                "speaker": "项目经理",
                "content": "Sprint周期定为1周，每周五下午进行复盘。小步快跑、快速迭代。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-01-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "1周sprint节奏有点快，中间插不进去技术调研。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-02-01T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "周五复盘时间能不能改到周四？"
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-02-15T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "1周确实太短，很多task做不完。"
            },
            {
                "event_id": "noise_4",
                "timestamp": "2026-02-28T14:00:00",
                "source": "feishu_group",
                "speaker": "产品经理",
                "content": "Sprint长度要不要调整？收集一下大家意见。"
            },
            {
                "event_id": "noise_5",
                "timestamp": "2026-03-05T09:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "2周sprint比较合理，有足够时间做开发。"
            },
            {
                "event_id": "noise_6",
                "timestamp": "2026-03-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "大多数公司都用2周sprint。"
            },
            {
                "event_id": "e2",
                "timestamp": "2026-03-15T10:00:00",
                "source": "feishu_group",
                "speaker": "项目经理",
                "content": "综合团队反馈，Sprint周期调整为2周，复盘改为隔周周五。1周sprint的快速迭代理念保留，改为每周三站会同步进度。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_7", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "2周sprint舒服多了。"},
            {"event_id": "noise_8", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "以前1周sprint的时候每天都很赶。"}
        ],
        "query": "我们的Sprint周期经历过什么变化？当前是多长？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "decision",
            "current_value": "2周",
            "inactive_values": ["1周"],
            "forbidden_active_values": ["1周"],
            "allow_historical_mention": True,
            "answer_keywords": ["2周", "1周", "调整"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    # ============================================================
    # abstention (3 new: dec_abs_003 ~ dec_abs_005)
    # ============================================================

    {
        "case_id": "dec_abs_003",
        "category": "decision_memory",
        "test_type": "abstention",
        "scenario": "语义邻近但实际未讨论过的主题拒答",
        "difficulty": "medium",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "微服务间通信采用gRPC，性能好且支持强类型。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-03-15T10:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "服务注册与发现采用Consul，配合健康检查。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-03-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "gRPC的protobuf定义需要统一管理。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "服务网格需要调研一下。"
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-04-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "Istio还是Linkerd？有人研究过吗？"
            },
            {
                "event_id": "noise_4",
                "timestamp": "2026-04-20T14:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "服务网格可以解决很多通信问题。"
            }
        ],
        "query": "我们服务网格选了Istio还是Linkerd？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未找到", "不确定", "没有相关", "尚未确定", "没有决定"],
            "hallucination_triggers": ["Istio", "Linkerd", "选择了"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate"]
    },

    {
        "case_id": "dec_abs_004",
        "category": "decision_memory",
        "test_type": "abstention",
        "scenario": "未参与项目的决策查询拒答",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "Alpha项目使用React前端框架。",
                "context": {"project": "Alpha"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-10T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "Beta项目使用Vue3前端框架。",
                "context": {"project": "Beta"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-05T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "React 19发布了，Alpha项目要升级吗？",
                "context": {"project": "Alpha"}
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-15T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "Vue3的Composition API真不错。",
                "context": {"project": "Beta"}
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-04-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "听说Delta项目也要启动了，有人知道技术栈吗？"
            }
        ],
        "query": "Delta项目前端用的什么框架？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未找到", "不确定", "没有相关", "Delta", "没有信息"],
            "hallucination_triggers": ["React", "Vue", "Angular"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate"]
    },

    {
        "case_id": "dec_abs_005",
        "category": "decision_memory",
        "test_type": "abstention",
        "scenario": "讨论过但从未做出最终决策的拒答",
        "difficulty": "hard",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-01T10:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "监控方案调研中，备选有Prometheus+Grafana、Datadog、New Relic。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-03-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "Prometheus是开源的，成本低。"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-03-15T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "Datadog功能全但贵。"
            },
            {
                "event_id": "noise_3",
                "timestamp": "2026-03-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "New Relic的APM做得不错。"
            },
            {
                "event_id": "noise_4",
                "timestamp": "2026-03-25T14:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "要不要每个方案都搭个POC？"
            },
            {
                "event_id": "noise_5",
                "timestamp": "2026-04-01T09:00:00",
                "source": "feishu_group",
                "speaker": "架构师",
                "content": "监控方案还没有最终决定，大家继续试用。"
            },
            {
                "event_id": "noise_6",
                "timestamp": "2026-04-10T10:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "Prometheus的Grafana面板我配了几个。"
            },
            {
                "event_id": "noise_7",
                "timestamp": "2026-04-20T10:00:00",
                "source": "feishu_group",
                "speaker": "成员C",
                "content": "Datadog试用期快到了。"
            },
            {
                "event_id": "noise_8",
                "timestamp": "2026-04-25T11:00:00",
                "source": "feishu_group",
                "speaker": "产品经理",
                "content": "监控选型什么时候能定？"
            }
        ],
        "query": "我们的监控系统最终选了什么方案？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未确定", "尚未决定", "还在调研", "没有最终", "未找到"],
            "hallucination_triggers": ["Prometheus", "Datadog", "New Relic", "选定了"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate", "noise_robustness"]
    }
]


def main():
    # Path to existing JSONL
    jsonl_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datasets", "decision_memory.jsonl"
    )

    # Read existing cases
    with open(jsonl_path, "r", encoding="utf-8") as f:
        existing = [line.strip() for line in f if line.strip()]

    print(f"Existing cases: {len(existing)}")

    # Validate new cases have unique case_ids
    existing_ids = set()
    for line in existing:
        case = json.loads(line)
        existing_ids.add(case["case_id"])

    new_ids = set()
    for case in NEW_CASES:
        cid = case["case_id"]
        if cid in existing_ids:
            print(f"ERROR: Duplicate case_id {cid}")
            return
        if cid in new_ids:
            print(f"ERROR: Duplicate new case_id {cid}")
            return
        new_ids.add(cid)

    # Append new cases
    with open(jsonl_path, "a", encoding="utf-8") as f:
        for case in NEW_CASES:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    print(f"Added {len(NEW_CASES)} new cases")
    print(f"Total cases: {len(existing) + len(NEW_CASES)}")

    # Print distribution
    all_cases = existing + [json.dumps(c, ensure_ascii=False) for c in NEW_CASES]
    type_dist = {}
    diff_dist = {}
    for line in all_cases:
        case = json.loads(line)
        tt = case["test_type"]
        type_dist[tt] = type_dist.get(tt, 0) + 1
        d = case["difficulty"]
        diff_dist[d] = diff_dist.get(d, 0) + 1

    print(f"\nTest type distribution:")
    for k, v in sorted(type_dist.items()):
        print(f"  {k}: {v}")

    print(f"\nDifficulty distribution:")
    for k, v in sorted(diff_dist.items()):
        print(f"  {k}: {v}")

    print(f"\nNew case IDs: {sorted(new_ids)}")
    print("Done!")


if __name__ == "__main__":
    main()
