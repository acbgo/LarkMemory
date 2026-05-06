#!/usr/bin/env python3

import json
import os

NEW_CASES = [
    # ============================================================
    # retrieval_recall (6 new: kh_ret_003 ~ kh_ret_008)
    # ============================================================

    {
        "case_id": "kh_ret_003",
        "category": "knowledge_health",
        "test_type": "retrieval_recall",
        "scenario": "3天前创建的团队知识应被标记为fresh并可召回",
        "difficulty": "easy",
        "time_span_days": 3,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-05-02T10:00:00",
                "source": "feishu_doc",
                "speaker": "前端负责人",
                "content": "前端框架已升级到React 18.3，支持Concurrent Features。所有新组件使用Concurrent Mode开发。",
                "context": {"project": "LarkMemory", "team": "frontend"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-05-03T14:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "React 18.3的Concurrent Features文档看了吗？Suspense改进很大。",
                "context": {"project": "LarkMemory", "team": "frontend"}
            },
            {
                "event_id": "e3",
                "timestamp": "2026-05-04T09:00:00",
                "source": "feishu_group",
                "speaker": "成员B",
                "content": "已经在用了，新的startTransition API很方便。",
                "context": {"project": "LarkMemory", "team": "frontend"}
            }
        ],
        "query": "我们前端框架升级到什么版本了？有什么新特性？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["React 18.3", "Concurrent Features", "Concurrent Mode"],
            "freshness_accuracy": True,
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "freshness_accuracy", "evidence_match"]
    },

    {
        "case_id": "kh_ret_004",
        "category": "knowledge_health",
        "test_type": "retrieval_recall",
        "scenario": "20天前创建的团队成员信息应可召回但标记为需验证",
        "difficulty": "medium",
        "time_span_days": 20,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "项目经理",
                "content": "后端组成员确认：张建国（架构师）、李明（高级开发）、王芳（数据库工程师）。这是当前团队配置。",
                "context": {"project": "LarkMemory", "team": "backend"}
            },
            {
                "event_id": "noise_1",
                "timestamp": "2026-04-25T10:00:00",
                "source": "feishu_group",
                "speaker": "成员A",
                "content": "后端组最近有新同事加入吗？"
            },
            {
                "event_id": "noise_2",
                "timestamp": "2026-04-30T10:00:00",
                "source": "feishu_group",
                "speaker": "项目经理",
                "content": "目前没变动，后续可能会有调整。"
            }
        ],
        "query": "后端组目前有哪些成员？各自的角色是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["张建国", "架构师", "李明", "高级开发", "王芳", "数据库工程师"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "freshness_accuracy", "evidence_match"]
    },

    {
        "case_id": "kh_ret_005",
        "category": "knowledge_health",
        "test_type": "retrieval_recall",
        "scenario": "核心API文档虽已创建60天但频繁被访问保持新鲜",
        "difficulty": "medium",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-05T10:00:00",
                "source": "feishu_doc",
                "speaker": "架构师",
                "content": "核心API接口文档：用户服务RESTful API v2.0，包含认证、用户管理、权限管理三大模块。认证使用JWT，用户管理支持CRUD，权限管理基于RBAC。",
                "context": {"project": "LarkMemory", "team": "backend"}
            },
            {"event_id": "access_1", "timestamp": "2026-03-10T09:00:00", "source": "feishu_group", "speaker": "成员A", "content": "查一下API文档，用户管理接口的请求格式是什么？"},
            {"event_id": "access_2", "timestamp": "2026-03-20T14:00:00", "source": "feishu_group", "speaker": "成员B", "content": "权限管理接口需要admin角色吗？参考API文档。"},
            {"event_id": "access_3", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "认证接口的JWT过期时间是多久？看看API文档。"},
            {"event_id": "access_4", "timestamp": "2026-04-15T11:00:00", "source": "feishu_group", "speaker": "成员A", "content": "用户管理批量删除接口文档里有说明吗？"},
            {"event_id": "access_5", "timestamp": "2026-04-28T09:00:00", "source": "feishu_group", "speaker": "成员D", "content": "API文档里RBAC的具体权限矩阵在哪里？"}
        ],
        "query": "核心API文档包含哪些模块？认证方式是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["v2.0", "认证", "用户管理", "权限管理", "JWT", "RBAC"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "freshness_accuracy", "evidence_match"]
    },

    {
        "case_id": "kh_ret_006",
        "category": "knowledge_health",
        "test_type": "retrieval_recall",
        "scenario": "含有明确过期日期的时效性知识自动标记",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "产品经理",
                "content": "产品V2.5定于2026年4月15日发布，需要提前3天完成回归测试。发布后旧版V2.4将在一个月后停止维护。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "V2.5回归测试进展正常。"},
            {"event_id": "noise_2", "timestamp": "2026-04-14T14:00:00", "source": "feishu_group", "speaker": "测试负责人", "content": "回归测试全部通过，明天可以发布。"},
            {"event_id": "e2", "timestamp": "2026-04-15T08:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "V2.5已正式发布！V2.4进入维护模式，5月15日彻底下线。"}
        ],
        "query": "V2.5产品的发布日期是什么？旧版本什么时候下线？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["4月15日", "V2.5", "V2.4", "5月15日"],
            "evidence_event_ids": ["e1", "e2"]
        },
        "metrics": ["recall_at_3", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_ret_007",
        "category": "knowledge_health",
        "test_type": "retrieval_recall",
        "scenario": "1天前强化的关键知识应保持高保留分数",
        "difficulty": "easy",
        "time_span_days": 7,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-28T10:00:00",
                "source": "feishu_group",
                "speaker": "DevOps",
                "content": "项目Grizzly的部署方案最终确认：Docker容器化 + K8s编排 + ArgoCD持续交付。所有人都需要了解这个流程。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "e2", "timestamp": "2026-04-29T09:00:00", "source": "feishu_group", "speaker": "成员A", "content": "再确认一下，Grizzly是用ArgoCD做持续交付对吧？"},
            {"event_id": "e3", "timestamp": "2026-04-29T10:00:00", "source": "feishu_group", "speaker": "DevOps", "content": "对，Docker + K8s + ArgoCD，记住这三个关键词。"},
            {"event_id": "noise_1", "timestamp": "2026-05-02T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "K8s集群升级到1.29了。"}
        ],
        "query": "Grizzly项目的部署方案是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["Docker", "K8s", "ArgoCD", "持续交付"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_ret_008",
        "category": "knowledge_health",
        "test_type": "retrieval_recall",
        "scenario": "30天前未强化的知识应显著降低置信度",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-05T10:00:00",
                "source": "feishu_group",
                "speaker": "行政",
                "content": "3月底团建去了密云古北水镇，玩了真人CS和篝火晚会。下次团建初步定在6月。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "上次团建去了哪里？有什么活动？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["古北水镇", "真人CS", "篝火晚会"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "evidence_match"]
    },

    # ============================================================
    # anti_interference (4 new: kh_anti_003 ~ kh_anti_006)
    # ============================================================

    {
        "case_id": "kh_anti_003",
        "category": "knowledge_health",
        "test_type": "anti_interference",
        "scenario": "高密度日常消息中召回CI/CD配置知识",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-05T10:00:00",
                "source": "feishu_doc",
                "speaker": "DevOps",
                "content": "CI/CD流水线配置标准：GitHub Actions触发，build阶段用Docker多阶段构建，deploy阶段用Helm chart部署到K8s。所有项目统一使用此流程。",
                "context": {"project": "LarkMemory", "team": "devops"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-06T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "今天代码review会议几点？"},
            {"event_id": "noise_2", "timestamp": "2026-04-08T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Jenkins pipeline好像比GitHub Actions更灵活。"},
            {"event_id": "noise_3", "timestamp": "2026-04-10T14:00:00", "source": "feishu_group", "speaker": "成员C", "content": "有人用过GitLab CI吗？"},
            {"event_id": "noise_4", "timestamp": "2026-04-12T09:00:00", "source": "feishu_group", "speaker": "成员A", "content": "今天午饭吃什么？"},
            {"event_id": "noise_5", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "CircleCI也挺好用的。"},
            {"event_id": "noise_6", "timestamp": "2026-04-18T11:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Docker build缓存怎么优化？"},
            {"event_id": "noise_7", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Helm chart的values文件管理有什么最佳实践？"},
            {"event_id": "noise_8", "timestamp": "2026-04-22T14:00:00", "source": "feishu_group", "speaker": "成员A", "content": "下周sprint planning准备一下。"},
            {"event_id": "noise_9", "timestamp": "2026-04-25T09:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "新需求PRD发群里了。"},
            {"event_id": "noise_10", "timestamp": "2026-04-28T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "CI跑挂了有人看看吗？"}
        ],
        "query": "我们CI/CD流水线的标准配置是什么？构建和部署分别用什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["GitHub Actions", "Docker", "多阶段构建", "Helm chart", "K8s"],
            "forbidden_active_values": ["Jenkins", "GitLab CI", "CircleCI"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    {
        "case_id": "kh_anti_004",
        "category": "knowledge_health",
        "test_type": "anti_interference",
        "scenario": "跨项目相似技术噪声中精确召回本项目的合规知识",
        "difficulty": "hard",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-10T10:00:00",
                "source": "feishu_doc",
                "speaker": "安全负责人",
                "content": "LarkMemory项目安全合规要求：所有API必须使用HTTPS + mTLS，JWT有效期不超过2小时，敏感数据必须AES-256加密存储。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Alpha项目的安全策略是只用HTTPS就够了。", "context": {"project": "Alpha"}},
            {"event_id": "noise_2", "timestamp": "2026-03-20T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Beta项目用的是OAuth2认证。", "context": {"project": "Beta"}},
            {"event_id": "noise_3", "timestamp": "2026-03-25T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Gamma项目JWT有效期设了24小时。"},
            {"event_id": "noise_4", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Alpha的加密用RSA就行了。"},
            {"event_id": "noise_5", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "有没有项目用国密SM4的？"},
            {"event_id": "noise_6", "timestamp": "2026-04-20T14:00:00", "source": "feishu_group", "speaker": "成员B", "content": "我们Beta项目不需要mTLS吧。"},
            {"event_id": "noise_7", "timestamp": "2026-04-30T09:00:00", "source": "feishu_group", "speaker": "成员C", "content": "JWT有效期2小时是不是太短了？"},
            {"event_id": "noise_8", "timestamp": "2026-05-02T10:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "安全合规文档需要更新了。"}
        ],
        "query": "LarkMemory项目的安全合规要求有哪些？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["HTTPS", "mTLS", "JWT", "2小时", "AES-256"],
            "forbidden_active_values": ["OAuth2", "24小时", "RSA"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    {
        "case_id": "kh_anti_005",
        "category": "knowledge_health",
        "test_type": "anti_interference",
        "scenario": "大量无关群聊中召回客户要求的关键知识",
        "difficulty": "medium",
        "time_span_days": 14,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-22T10:00:00",
                "source": "feishu_group",
                "speaker": "客户经理",
                "content": "重要：客户华兴银行要求所有报表必须支持导出为PDF格式，且需要包含电子签名。这是合同里的硬性要求。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-23T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "PDF导出功能谁来做？"},
            {"event_id": "noise_2", "timestamp": "2026-04-24T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Excel导出也要做吗？"},
            {"event_id": "noise_3", "timestamp": "2026-04-25T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "CSV格式其实更方便。"},
            {"event_id": "noise_4", "timestamp": "2026-04-26T14:00:00", "source": "feishu_group", "speaker": "成员A", "content": "电子签名用哪个第三方？"},
            {"event_id": "noise_5", "timestamp": "2026-04-28T09:00:00", "source": "feishu_group", "speaker": "成员D", "content": "Markdown也能导出PDF。"},
            {"event_id": "noise_6", "timestamp": "2026-04-30T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "客户说要JSON格式的行不行？"},
            {"event_id": "noise_7", "timestamp": "2026-05-02T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "报表模板我设计好了。"},
            {"event_id": "noise_8", "timestamp": "2026-05-04T11:00:00", "source": "feishu_group", "speaker": "成员C", "content": "电子签名的SDK文档在哪里？"}
        ],
        "query": "华兴银行客户对报表有什么硬性要求？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["华兴银行", "PDF", "电子签名", "合同"],
            "forbidden_active_values": ["Excel", "CSV", "JSON"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    {
        "case_id": "kh_anti_006",
        "category": "knowledge_health",
        "test_type": "anti_interference",
        "scenario": "服务器配置信息批量噪声中召回当前架构",
        "difficulty": "hard",
        "time_span_days": 120,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-12-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "架构师",
                "content": "公司技术架构标准：前端React+Next.js，后端Go+gRPC，数据库PostgreSQL+Redis，部署K8s。新项目必须遵循此标准。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-01-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "旧服务器集群A配置：8核16G，CentOS 7，已退役。"},
            {"event_id": "noise_2", "timestamp": "2026-01-20T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "旧服务器集群B配置：16核32G，Ubuntu 22.04，还在用。"},
            {"event_id": "noise_3", "timestamp": "2026-02-01T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "旧数据库主从配置：MySQL 8.0双主模式，已迁移。"},
            {"event_id": "noise_4", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Ansible playbook v1还可以用吗？"},
            {"event_id": "noise_5", "timestamp": "2026-03-01T14:00:00", "source": "feishu_group", "speaker": "成员B", "content": "前端要不要换Vue？"},
            {"event_id": "noise_6", "timestamp": "2026-03-15T09:00:00", "source": "feishu_group", "speaker": "成员C", "content": "后端用Java还是Go？之前不是说用Java吗？"},
            {"event_id": "noise_7", "timestamp": "2026-03-30T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "MongoDB比PostgreSQL适合文档存储。"},
            {"event_id": "noise_8", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "K8s版本需要升级到1.30。"},
            {"event_id": "noise_9", "timestamp": "2026-04-25T11:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Next.js 15发布了要不要试一下？"},
            {"event_id": "noise_10", "timestamp": "2026-04-30T10:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "技术架构文档更新了没有？"}
        ],
        "query": "当前公司的标准技术架构是什么？各层用什么技术？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["React", "Next.js", "Go", "gRPC", "PostgreSQL", "Redis", "K8s"],
            "forbidden_active_values": ["Vue", "Java", "MongoDB", "MySQL"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "noise_robustness", "evidence_match"]
    },

    # ============================================================
    # contradiction_update (5 new: kh_contra_003 ~ kh_contra_007)
    # ============================================================

    {
        "case_id": "kh_contra_003",
        "category": "knowledge_health",
        "test_type": "contradiction_update",
        "scenario": "API端点版本升级v1到v2旧版标记为superseded",
        "difficulty": "medium",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "后端负责人",
                "content": "用户服务API端点：https://api.example.com/v1/users，支持基本CRUD操作。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "v1 API返回格式需要调整一下。"},
            {"event_id": "e2", "timestamp": "2026-04-01T10:00:00", "source": "feishu_doc", "speaker": "后端负责人", "content": "用户服务API升级到v2：https://api.example.com/v2/users。v2支持批量操作和分页，v1将在5月1日下线。新功能必须基于v2开发。", "context": {"project": "LarkMemory"}},
            {"event_id": "noise_2", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "v2的批量导入接口文档在哪里？"},
            {"event_id": "noise_3", "timestamp": "2026-04-28T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "v1还有人在用吗？"}
        ],
        "query": "当前用户服务API端点是什么版本？v1还能用吗？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "current_value": "v2",
            "inactive_values": ["v1"],
            "forbidden_active_values": ["v1"],
            "allow_historical_mention": True,
            "answer_keywords": ["v2", "v1", "5月1日", "下线"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "expired_memory_suppression", "evidence_match"]
    },

    {
        "case_id": "kh_contra_004",
        "category": "knowledge_health",
        "test_type": "contradiction_update",
        "scenario": "数据库配置经历MySQL 5.7→8.0→PostgreSQL 15三版本演进",
        "difficulty": "hard",
        "time_span_days": 365,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-05-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "DBA",
                "content": "数据库配置：MySQL 5.7 @ localhost:3306，字符集utf8mb4。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2025-11-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "DBA",
                "content": "数据库升级到MySQL 8.0 @ db-staging.example.com:3306，主要改进：窗口函数、CTE、JSON增强。旧5.7实例已停用。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-01-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "MySQL 8.0的窗口函数比5.7好用太多了。"},
            {"event_id": "noise_2", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "PostgreSQL的JSON支持比MySQL强。"},
            {"event_id": "noise_3", "timestamp": "2026-03-01T14:00:00", "source": "feishu_group", "speaker": "架构师", "content": "我们是不是该考虑换PostgreSQL？MySQL的许可证有风险。"},
            {
                "event_id": "e3",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "DBA",
                "content": "数据库已迁移到PostgreSQL 15 @ db-prod.example.com:5432。迁移原因：许可证合规、更强大的JSON支持、更好的全文搜索。MySQL实例已归档。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "我们数据库经历过哪些版本？当前用的是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "current_value": "PostgreSQL 15",
            "inactive_values": ["MySQL 5.7", "MySQL 8.0"],
            "forbidden_active_values": ["MySQL"],
            "allow_historical_mention": True,
            "answer_keywords": ["PostgreSQL 15", "MySQL 5.7", "MySQL 8.0", "许可证", "JSON"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1", "e2"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    {
        "case_id": "kh_contra_005",
        "category": "knowledge_health",
        "test_type": "contradiction_update",
        "scenario": "日志级别经历INFO→DEBUG→WARN三次变更有完整changelog",
        "difficulty": "medium",
        "time_span_days": 90,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "运维",
                "content": "生产环境日志级别设置为INFO，这是标准配置。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-03-01T10:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "排查订单丢失问题，临时把日志级别改成了DEBUG。问题修复后会改回去。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "DEBUG日志太多了磁盘快满了。"},
            {
                "event_id": "e3",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_group",
                "speaker": "后端负责人",
                "content": "订单丢失问题已修复，日志级别调整为WARN以降低存储成本。INFO已废弃不用。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "目前生产环境日志级别是什么？之前有过哪些变化？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "current_value": "WARN",
            "inactive_values": ["INFO", "DEBUG"],
            "forbidden_active_values": ["INFO", "DEBUG"],
            "allow_historical_mention": True,
            "answer_keywords": ["WARN", "INFO", "DEBUG", "存储成本"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1", "e2"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    {
        "case_id": "kh_contra_006",
        "category": "knowledge_health",
        "test_type": "contradiction_update",
        "scenario": "SSH端口错误修改后回滚到旧版本",
        "difficulty": "hard",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "运维",
                "content": "SSH端口配置：默认22端口。安全策略要求使用非标准端口。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-15T10:00:00",
                "source": "feishu_group",
                "speaker": "运维",
                "content": "SSH端口已改为2222，防火墙上已放行。请更新SSH配置。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-16T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "连不上服务器了，2222端口不通。"},
            {"event_id": "noise_2", "timestamp": "2026-04-16T11:00:00", "source": "feishu_group", "speaker": "成员B", "content": "防火墙规则有问题，外网访问不了2222。"},
            {
                "event_id": "e3",
                "timestamp": "2026-04-16T14:00:00",
                "source": "feishu_group",
                "speaker": "运维",
                "content": "2222端口配置有误导致外网无法访问，紧急回退到22端口。2222配置废弃不用，之后重新选端口。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "当前SSH端口是多少？2222端口还在用吗？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "current_value": "22",
            "inactive_values": ["2222"],
            "forbidden_active_values": ["2222"],
            "allow_historical_mention": True,
            "answer_keywords": ["22", "回退", "2222", "废弃"],
            "evidence_event_ids": ["e3"],
            "superseded_event_ids": ["e1", "e2"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    {
        "case_id": "kh_contra_007",
        "category": "knowledge_health",
        "test_type": "contradiction_update",
        "scenario": "安全策略更新后部分成员未确认同步",
        "difficulty": "medium",
        "time_span_days": 21,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "安全负责人",
                "content": "旧安全策略：服务间通信用HTTP，JWT有效期24小时。",
                "context": {"project": "LarkMemory"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-04-20T10:00:00",
                "source": "feishu_group",
                "speaker": "安全负责人",
                "content": "新安全策略上线：所有服务间通信必须使用mTLS加密，JWT有效期从24小时缩短到2小时。@所有人请确认知悉！",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-21T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "收到，mTLS配置已经更新。"},
            {"event_id": "noise_2", "timestamp": "2026-04-22T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "JWT有效期2小时的话需要加refresh token机制。"},
            {"event_id": "noise_3", "timestamp": "2026-04-25T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "我之前用的还是24小时的JWT，需要更新吗？"}
        ],
        "query": "当前服务间通信安全策略是什么？JWT有效期是多久？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "current_value": "mTLS",
            "inactive_values": ["HTTP"],
            "forbidden_active_values": ["HTTP", "24小时"],
            "allow_historical_mention": True,
            "answer_keywords": ["mTLS", "2小时", "JWT"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["latest_value_accuracy", "old_value_suppression", "evidence_match"]
    },

    # ============================================================
    # long_term_retention (6 new: kh_long_003 ~ kh_long_008)
    # ============================================================

    {
        "case_id": "kh_long_003",
        "category": "knowledge_health",
        "test_type": "long_term_retention",
        "scenario": "90天前的Q1技术评审结论跨季度召回",
        "difficulty": "hard",
        "time_span_days": 95,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-30T10:00:00",
                "source": "feishu_doc",
                "speaker": "架构师",
                "content": "Q1技术评审结论：前端性能优化采用方案A（代码分割 + Tree Shaking + 懒加载），后端采用方案B（Redis缓存 + 异步队列解耦）。所有团队需按此方案执行。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "方案A的代码分割效果明显，首屏加载快了50%。"},
            {"event_id": "noise_2", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "异步队列用了Redis Stream还是RabbitMQ？"},
            {"event_id": "noise_3", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Tree Shaking需要ES Module才能生效。"},
            {"event_id": "noise_4", "timestamp": "2026-04-01T14:00:00", "source": "feishu_group", "speaker": "成员A", "content": "前端要不要再加个SSR？"},
            {"event_id": "noise_5", "timestamp": "2026-04-15T09:00:00", "source": "feishu_group", "speaker": "产品经理", "content": "Q2技术评审会什么时候开？"},
            {"event_id": "noise_6", "timestamp": "2026-04-30T10:00:00", "source": "feishu_group", "speaker": "成员D", "content": "方案B的缓存命中率是多少？"}
        ],
        "query": "Q1技术评审的结论是什么？前端和后端分别采用了什么优化方案？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["方案A", "代码分割", "Tree Shaking", "懒加载", "方案B", "Redis", "异步队列"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_long_004",
        "category": "knowledge_health",
        "test_type": "long_term_retention",
        "scenario": "120天前创建的旧项目知识应被标记为遗忘但可召回",
        "difficulty": "hard",
        "time_span_days": 120,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-12-30T10:00:00",
                "source": "feishu_doc",
                "speaker": "前任技术经理",
                "content": "旧项目Sparrow的数据库连接信息：mysql://sparrow-db:3306，用户名sparrow_app，数据库名sparrow_production。该项目已于2025年6月停止维护。",
                "context": {"project": "Sparrow"}
            }
        ],
        "query": "旧项目Sparrow的数据库连接信息是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["Sparrow", "mysql", "3306", "sparrow_production"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_long_005",
        "category": "knowledge_health",
        "test_type": "long_term_retention",
        "scenario": "高重要性但长期未访问的知识触发遗忘预警",
        "difficulty": "hard",
        "time_span_days": 90,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-30T10:00:00",
                "source": "feishu_doc",
                "speaker": "项目经理",
                "content": "Q1规划目标：完成用户系统重构和支付模块升级，目标3月底上线。涉及4个团队12名开发人员。这是年度核心目标。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "用户系统重构进度正常。"},
            {"event_id": "noise_2", "timestamp": "2026-03-30T10:00:00", "source": "feishu_group", "speaker": "项目经理", "content": "Q1目标已完成，进入Q2规划阶段。"},
            {"event_id": "noise_3", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Q2目标是做什么？有人记得Q1定的后续方向吗？"}
        ],
        "query": "Q1的规划目标是什么？涉及多少人员？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["用户系统重构", "支付模块升级", "3月底", "12名"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_long_006",
        "category": "knowledge_health",
        "test_type": "long_term_retention",
        "scenario": "一年前创建的架构标准持续被使用保持新鲜",
        "difficulty": "hard",
        "time_span_days": 330,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-06-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "CTO",
                "content": "公司技术架构标准v1.0：前端React+Next.js，后端Go+gRPC，数据库PostgreSQL+Redis，部署K8s。每季度review一次。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "e2", "timestamp": "2025-09-01T10:00:00", "source": "feishu_group", "speaker": "架构师", "content": "Q3架构review：当前架构标准不变，继续使用React+Go+PostgreSQL+K8s。"},
            {"event_id": "e3", "timestamp": "2025-12-01T10:00:00", "source": "feishu_group", "speaker": "架构师", "content": "Q4架构review：标准保持不变。新增Redis缓存层已纳入标准。"},
            {"event_id": "e4", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "架构师", "content": "Q1架构review：标准继续沿用。K8s版本升级到1.30。"},
            {"event_id": "noise_1", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "新来的同事问我们技术栈是什么？"}
        ],
        "query": "公司的标准技术架构是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["React", "Next.js", "Go", "gRPC", "PostgreSQL", "Redis", "K8s"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_long_007",
        "category": "knowledge_health",
        "test_type": "long_term_retention",
        "scenario": "批量旧服务器配置知识180天无人访问应触发批量预警",
        "difficulty": "hard",
        "time_span_days": 180,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2025-10-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "运维",
                "content": "旧服务器集群配置清单：A集群8核16G CentOS 7（已退役）、B集群16核32G Ubuntu 22.04（备用）、旧数据库MySQL 8.0双主模式（已迁移）、Ansible playbook v1（已废弃）、旧环境变量配置模板（已废弃）。以上配置仅供参考，生产环境已全部迁移。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "旧服务器集群的配置清单还有哪些？哪些已退役？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["CentOS 7", "已退役", "Ubuntu 22.04", "备用", "MySQL 8.0", "已迁移"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_long_008",
        "category": "knowledge_health",
        "test_type": "long_term_retention",
        "scenario": "安全审计知识接近遗忘阈值应触发预警",
        "difficulty": "hard",
        "time_span_days": 73,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-02-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "安全负责人",
                "content": "安全审计发现3个高危漏洞需要修复：SQL注入（用户输入未过滤）、XSS（富文本编辑器）、CSRF（表单无token）。修复截止日期3月1日。这是最高优先级安全事项。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "e2", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "后端负责人", "content": "三个高危漏洞已全部修复。SQL注入增加了参数化查询，XSS加了DOMPurify，CSRF加了token验证。"},
            {"event_id": "noise_1", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "新的安全扫描工具要不要试一下？"},
            {"event_id": "noise_2", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "最近没有新的安全漏洞吧？"}
        ],
        "query": "上次安全审计发现了哪些高危漏洞？修复方案是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["SQL注入", "XSS", "CSRF", "参数化查询", "DOMPurify", "token"],
            "evidence_event_ids": ["e1", "e2"]
        },
        "metrics": ["recall_at_3", "long_term_recall", "keyword_match", "evidence_match"]
    },

    # ============================================================
    # cross_project (4 new: kh_xproj_001 ~ kh_xproj_004)
    # ============================================================

    {
        "case_id": "kh_xproj_001",
        "category": "knowledge_health",
        "test_type": "cross_project",
        "scenario": "跨项目知识分布不均检测——Project Bison文档严重缺失",
        "difficulty": "medium",
        "time_span_days": 60,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "技术经理",
                "content": "Project Antelope文档清单：部署文档5篇、架构文档3篇、API文档8篇。文档覆盖完整。",
                "context": {"project": "Antelope"}
            },
            {
                "event_id": "e2",
                "timestamp": "2026-03-15T10:00:00",
                "source": "feishu_doc",
                "speaker": "技术经理",
                "content": "Project Bison文档清单：部署文档0篇、架构文档仅1篇（不完整）、API文档0篇。急需补充文档。",
                "context": {"project": "Bison"}
            },
            {"event_id": "noise_1", "timestamp": "2026-03-20T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "Antelope的API文档很详细。", "context": {"project": "Antelope"}},
            {"event_id": "noise_2", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Bison项目连部署文档都没有，新人不知道怎么部署。"},
            {"event_id": "noise_3", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "Antelope的架构文档可以当模板参考。"}
        ],
        "query": "Project Bison的文档覆盖情况如何？缺少哪些文档？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["Bison", "部署文档", "0篇", "架构文档", "1篇", "API文档"],
            "forbidden_active_values": ["5篇", "8篇", "完整"],
            "evidence_event_ids": ["e2"],
            "superseded_event_ids": ["e1"]
        },
        "metrics": ["scope_accuracy", "cross_project_leakage_rate", "evidence_match"]
    },

    {
        "case_id": "kh_xproj_002",
        "category": "knowledge_health",
        "test_type": "cross_project",
        "scenario": "安全领域知识仅1条浅覆盖应被识别为深度不足",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "安全负责人",
                "content": "LarkMemory安全知识库当前仅有一条：所有API必须使用HTTPS。还需补充：认证鉴权机制、数据加密标准、安全审计流程、渗透测试指南。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "我们安全相关的文档太少了。"},
            {"event_id": "noise_2", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "渗透测试需要专门的文档吗？"},
            {"event_id": "noise_3", "timestamp": "2026-04-25T10:00:00", "source": "feishu_group", "speaker": "安全负责人", "content": "安全知识还在建设中，目前覆盖严重不足。"}
        ],
        "query": "LarkMemory项目的安全知识覆盖情况如何？有哪些缺口？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["HTTPS", "不足", "认证鉴权", "数据加密", "安全审计", "渗透测试"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["scope_accuracy", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_xproj_003",
        "category": "knowledge_health",
        "test_type": "cross_project",
        "scenario": "新人入职知识缺口检测——仅1/5文档就绪",
        "difficulty": "medium",
        "time_span_days": 14,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-20T10:00:00",
                "source": "feishu_doc",
                "speaker": "技术经理",
                "content": "新员工刘洋下周入职，需要的onboarding文档：开发环境搭建指南（已有）、代码规范文档（已有）、Git工作流说明（缺失）、部署流程文档（缺失）、常见问题FAQ（缺失）。紧急补充中。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-22T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "开发环境搭建指南我已经更新了。"},
            {"event_id": "noise_2", "timestamp": "2026-04-25T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "Git工作流文档我来写吧。"},
            {"event_id": "noise_3", "timestamp": "2026-04-28T10:00:00", "source": "feishu_group", "speaker": "技术经理", "content": "刘洋下周就到了，部署流程和FAQ还没写。"}
        ],
        "query": "新员工入职需要哪些文档？哪些还没有准备好？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["刘洋", "开发环境搭建", "代码规范", "Git工作流", "缺失", "部署流程", "FAQ"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["scope_accuracy", "keyword_match", "evidence_match"]
    },

    {
        "case_id": "kh_xproj_004",
        "category": "knowledge_health",
        "test_type": "cross_project",
        "scenario": "跨项目团队知识覆盖对比——前端vs后端vs DevOps vs 数据库",
        "difficulty": "hard",
        "time_span_days": 90,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-02-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "技术经理",
                "content": "团队知识覆盖统计：前端领域15条记录（React/Vue/CSS），后端8条（Go API/gRPC），DevOps 10条（Docker/K8s/CI/CD），数据库和安全领域0条。数据库和安全是明显缺口，需要尽快补充。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-15T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "前端文档已经比较完善了。"},
            {"event_id": "noise_2", "timestamp": "2026-03-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "后端还需要补充数据库相关的文档。"},
            {"event_id": "noise_3", "timestamp": "2026-03-15T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "安全的文档我来负责写。"},
            {"event_id": "noise_4", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "技术经理", "content": "数据库文档还是0条，这个问题很严重。"}
        ],
        "query": "哪些领域的团队知识覆盖是空的？哪些最完善？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["数据库", "安全", "0条", "前端", "15条", "DevOps"],
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["scope_accuracy", "keyword_match", "evidence_match"]
    },

    # ============================================================
    # abstention (4 new: kh_abs_002 ~ kh_abs_005)
    # ============================================================

    {
        "case_id": "kh_abs_002",
        "category": "knowledge_health",
        "test_type": "abstention",
        "scenario": "团队知识库中不存在的内容应正确拒答",
        "difficulty": "medium",
        "time_span_days": 30,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-01T10:00:00",
                "source": "feishu_doc",
                "speaker": "技术经理",
                "content": "前端使用React 18 + TypeScript，后端使用Go 1.22 + gRPC。数据库PostgreSQL 15。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "我们有没有消息队列相关的文档？"},
            {"event_id": "noise_2", "timestamp": "2026-04-15T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "好像没有专门的消息队列选型文档。"},
            {"event_id": "noise_3", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "我也没找到，但听说之前讨论过用Kafka。"}
        ],
        "query": "我们的消息队列选型结论是什么？用的是Kafka还是别的？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未找到", "不确定", "没有相关", "没有文档", "尚未记录"],
            "hallucination_triggers": ["Kafka", "RabbitMQ", "Redis Stream", "选择了"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate"]
    },

    {
        "case_id": "kh_abs_003",
        "category": "knowledge_health",
        "test_type": "abstention",
        "scenario": "存在相似但不完全匹配的知识时正确拒答",
        "difficulty": "medium",
        "time_span_days": 45,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-03-20T10:00:00",
                "source": "feishu_doc",
                "speaker": "运维",
                "content": "生产环境部署在AWS us-east-1的EKS集群上，节点4台c5.2xlarge。这是当前配置。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "我们有Azure上的服务吗？"},
            {"event_id": "noise_2", "timestamp": "2026-04-10T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "印象中没有，全在AWS上。"},
            {"event_id": "noise_3", "timestamp": "2026-04-20T10:00:00", "source": "feishu_group", "speaker": "成员C", "content": "GCP呢？好像也没有。"}
        ],
        "query": "我们在Azure上的K8s集群配置是什么？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未找到", "没有Azure", "只在AWS", "不确定"],
            "hallucination_triggers": ["Azure", "Standard_D4s", "AKS", "eastus"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate"]
    },

    {
        "case_id": "kh_abs_004",
        "category": "knowledge_health",
        "test_type": "abstention",
        "scenario": "拼写近似但实际不存在的项目知识拒答",
        "difficulty": "easy",
        "time_span_days": 7,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-28T10:00:00",
                "source": "feishu_group",
                "speaker": "项目经理",
                "content": "Alpha项目的数据库是PostgreSQL，Beta项目的数据库是MongoDB。都记录在案了。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "Delta项目的数据库用的是什么？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未找到", "不确定", "没有Delta", "没有相关", "没有信息"],
            "hallucination_triggers": ["PostgreSQL", "MongoDB", "MySQL"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate"]
    },

    {
        "case_id": "kh_abs_005",
        "category": "knowledge_health",
        "test_type": "abstention",
        "scenario": "季节性过期知识的当下查询应拒答当前状态",
        "difficulty": "medium",
        "time_span_days": 120,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-01-05T10:00:00",
                "source": "feishu_doc",
                "speaker": "HR",
                "content": "2025年度年终总结模板和流程。绩效评估标准按2025年版本执行。此流程仅适用于2025年度。",
                "context": {"project": "LarkMemory"}
            },
            {"event_id": "noise_1", "timestamp": "2026-02-01T10:00:00", "source": "feishu_group", "speaker": "成员A", "content": "2025年终总结都交了吧？"},
            {"event_id": "noise_2", "timestamp": "2026-04-01T10:00:00", "source": "feishu_group", "speaker": "成员B", "content": "2026年的绩效标准出来了吗？"}
        ],
        "query": "2026年度的绩效评估标准是什么？",
        "expected": {
            "should_retrieve": False,
            "abstention_keywords": ["未找到", "尚未发布", "没有2026", "不确定"],
            "hallucination_triggers": ["2025", "年度"],
            "evidence_event_ids": []
        },
        "metrics": ["abstention_accuracy", "hallucination_rate"]
    },

    # ============================================================
    # efficiency (2 new: kh_eff_001 ~ kh_eff_002)
    # ============================================================

    {
        "case_id": "kh_eff_001",
        "category": "knowledge_health",
        "test_type": "efficiency",
        "scenario": "知识库加速故障排查——生产环境配置快速定位",
        "difficulty": "easy",
        "time_span_days": 7,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-28T10:00:00",
                "source": "feishu_doc",
                "speaker": "运维",
                "content": "生产环境完整配置清单：负载均衡ALB（端口443→3000），应用服务器3台c5.2xlarge（Node.js 20），数据库RDS PostgreSQL 15（db.r6g.2xlarge），缓存ElastiCache Redis 7.0（cache.r6g.large），CDN CloudFront，日志S3+CloudWatch。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "生产环境用了哪些AWS资源？各自的规格是什么？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["ALB", "c5.2xlarge", "RDS", "PostgreSQL", "ElastiCache", "Redis", "CloudFront"],
            "baseline_steps": 5,
            "min_saving_rate": 0.5,
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "step_saving_rate"]
    },

    {
        "case_id": "kh_eff_002",
        "category": "knowledge_health",
        "test_type": "efficiency",
        "scenario": "知识库减少重复提问——常见问题FAQ快速响应",
        "difficulty": "easy",
        "time_span_days": 14,
        "input_events": [
            {
                "event_id": "e1",
                "timestamp": "2026-04-22T10:00:00",
                "source": "feishu_doc",
                "speaker": "技术经理",
                "content": "常见问题FAQ更新：Q1-如何搭建开发环境？（见搭建指南），Q2-代码规范在哪里？（见.eslintrc和.prettierrc），Q3-如何部署到测试环境？（执行npm run deploy:staging），Q4-数据库迁移怎么跑？（npx prisma migrate dev），Q5-日志在哪里看？（CloudWatch Logs /logs/app）。",
                "context": {"project": "LarkMemory"}
            }
        ],
        "query": "如何部署到测试环境？",
        "expected": {
            "should_retrieve": True,
            "memory_type": "knowledge",
            "answer_keywords": ["npm run deploy:staging", "测试环境"],
            "baseline_steps": 3,
            "min_saving_rate": 0.6,
            "evidence_event_ids": ["e1"]
        },
        "metrics": ["recall_at_3", "keyword_match", "step_saving_rate"]
    }
]


def main():
    jsonl_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "datasets", "knowledge_health.jsonl"
    )

    # Read existing cases
    with open(jsonl_path, "r", encoding="utf-8") as f:
        existing = [line.strip() for line in f if line.strip()]

    print(f"Existing cases: {len(existing)}")

    # Validate unique case_ids
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
