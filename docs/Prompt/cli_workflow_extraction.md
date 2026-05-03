# CLI Workflow Memory — LLM 语义抽取 Prompt

## 1. 设计目标

LLM 负责从 OpenClaw 教学文本中抽取命令意图和参数语义，不负责命令模板的参数化（模板化由规则层完成）。

两种调用路径：

- **规则命中**（有完整命令或已知工具链前缀）：规则层已完成命令模板参数化（`--env prod` → `--env {env}`），LLM 只需为每个参数补充语义描述。
- **规则未命中**（场景词 + 参数片段，如"部署时提醒我用 --region cn-shanghai"）：LLM 需要同时抽取场景关键词和参数，并补充语义描述。

LLM 不负责：
- 命令模板的参数化（--env {env} 由规则层完成）
- 查找同项目下已有的命令模板（后端 extractor 负责）
- 决定 reinforce / supersede（版本管理层负责）

## 2. System Prompt

```text
你是一个 CLI 工作流命令参数语义分析器。

你的任务是从用户的命令教学中识别场景、参数和语义含义。你不需要生成完整的命令模板，只需要分析参数的语义含义。

请严格遵守：
1. 如果用户明确给出了完整命令（如"lark project deploy --env staging"），full_command 字段填写该命令
2. 如果用户只描述了场景但没有完整命令（如"部署时提醒我"），full_command 为 null，用 scenario_keywords 描述场景
3. parameters 中的每个参数必须包含语义解释（如 --env 在部署场景下表示"部署目标环境"）
4. 只返回 JSON，不要输出 Markdown、解释文字或额外字段
5. 不要编造用户没有提到的参数
```

## 3. 输出 JSON Schema

```json
{
  "type": "object",
  "required": ["scenario_keywords", "parameters", "is_teaching", "full_command"],
  "properties": {
    "full_command": {
      "type": "string|null",
      "description": "用户明确提到的完整命令。如果用户通过规则层已经提取出完整命令，这里为命令文本；如果用户只描述了场景没有完整命令，则为 null"
    },
    "scenario_keywords": {
      "type": "array",
      "items": {"type": "string"},
      "description": "命令使用场景的关键词，如['部署','staging环境']，用于后端匹配同项目下的已有命令模板"
    },
    "parameters": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["param_name", "param_value", "semantics"],
        "properties": {
          "param_name": {
            "type": "string",
            "description": "参数名，如 env、region、canary"
          },
          "param_value": {
            "type": "string",
            "description": "参数取值，如 staging、cn-shanghai、50"
          },
          "semantics": {
            "type": "string",
            "description": "该参数在当前场景下的语义含义，如'部署目标环境，staging 表示预发布环境'、'金丝雀发布流量百分比'"
          }
        }
      }
    },
    "is_teaching": {
      "type": "boolean",
      "description": "用户意图是否为显式命令教学"
    }
  }
}
```

## 4. 规则命中场景（已有完整命令，仅补语义）

User prompt：

```json
{
  "context_hint": "规则层已从用户消息中提取出完整命令模板。请只分析每个参数的语义含义。",
  "command": "lark project deploy --env staging --canary 50",
  "parameters": [
    {"param_name": "env", "param_value": "staging"},
    {"param_name": "canary", "param_value": "50"}
  ],
  "original_text": "记住：部署时用 lark project deploy --env staging --canary 50"
}
```

Expected output：

```json
{
  "full_command": "lark project deploy --env staging --canary 50",
  "scenario_keywords": ["部署", "staging环境"],
  "parameters": [
    {
      "param_name": "env",
      "param_value": "staging",
      "semantics": "部署目标环境，staging 表示预发布环境"
    },
    {
      "param_name": "canary",
      "param_value": "50",
      "semantics": "金丝雀发布策略的流量百分比，50 表示 50% 的流量先切换到新版本"
    }
  ],
  "is_teaching": true
}
```

## 5. 规则未命中场景（场景词 + 参数片段）

User prompt：

```json
{
  "context_hint": "用户给出了命令教学，但没有完整命令。请识别场景关键词和参数。",
  "original_text": "以后部署提醒我用 --region cn-shanghai"
}
```

Expected output：

```json
{
  "full_command": null,
  "scenario_keywords": ["部署"],
  "parameters": [
    {
      "param_name": "region",
      "param_value": "cn-shanghai",
      "semantics": "部署目标区域，cn-shanghai 表示中国上海区域"
    }
  ],
  "is_teaching": true
}
```

## 6. 非教学场景（无命令相关记忆）

User prompt：

```json
{
  "context_hint": "用户给出了命令教学，但没有完整命令。请识别场景关键词和参数。",
  "original_text": "早上好"
}
```

Expected output：

```json
{
  "full_command": null,
  "scenario_keywords": [],
  "parameters": [],
  "is_teaching": false
}
```
