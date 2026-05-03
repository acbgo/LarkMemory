# LarkMemory

LarkMemory 是飞书 AI 比赛 OpenClaw 赛道下的企业级长程协作 Memory 系统。当前后端采用本地 Python Memory Engine，提供事件写入、长期记忆落库、检索、更新和健康检查 API。

## 当前后端链路

当前已跑通最小闭环：

1. `POST /api/v1/ingest` 写入 `NormalizedEvent`。
2. `MemoryService` 调用 `project_decision` 规则抽取器。
3. 抽取出的项目决策转换为 `MemoryCore(domain="project_decision")` 并写入 SQLite。
4. `POST /api/v1/retrieve` 从 `MemoryCoreStore` 召回 active memory。
5. `POST /api/v1/update` 支持 expire、forget、supersede、confidence、importance、feedback。
6. `GET /health` 检查 SQLite event/memory store 可用性。

当前已接入真实飞书 API（WebSocket 消息监听、消息发送、卡片交互）、真实 LLM（OpenAI-compatible 抽取/Embedding/Rerank）、向量数据库（ChromaDB）和主动推送调度（team_retention 复习提醒）。暂不涉及生产级认证权限。

## 环境准备

建议使用 Python 3.11+，项目使用 `uv` 管理本地 Python 环境和依赖。

```bash
uv venv
uv pip install -r requirements.txt
```

## 运行测试

```bash
uv run pytest -q
uv run python -m compileall src tests
```

当前验证结果：

- `pytest -q`：152 passed, 1 skipped
- `python -m compileall src tests`：通过

## 启动后端服务

默认端口为 `8765`，默认 SQLite 路径为 `.larkmemory/larkmemory.db`。

推荐先修改根目录的 `larkmemory.env`，再正常启动服务。项目启动时会自动读取该配置文件；仓库提供 `larkmemory.env.example` 作为模板，真实 `larkmemory.env` 默认不提交。

```powershell
uv run uvicorn src.app.main:app --host 127.0.0.1 --port 8765
```

如果要使用其他配置文件，先设置 `LARKMEMORY_CONFIG_FILE` 指向它；真实环境变量优先级高于配置文件。

```powershell
$env:LARKMEMORY_CONFIG_FILE=".\larkmemory.env"
uv run uvicorn src.app.main:app --host 127.0.0.1 --port 8765
```

Linux/macOS 示例：

```bash
export LARKMEMORY_CONFIG_FILE=./larkmemory.env
uv run uvicorn src.app.main:app --host 127.0.0.1 --port 8765
```

```bash
uv run uvicorn src.app.main:app --host 127.0.0.1 --port 8765
```

也可以通过环境变量指定运行参数：

```bash
export LARKMEMORY_PORT=8765
export LARKMEMORY_SQLITE_PATH=.larkmemory/larkmemory.db
uv run uvicorn src.app.main:app --host 127.0.0.1 --port "$LARKMEMORY_PORT"
```

## 手工验证

### 健康检查

```bash
curl http://127.0.0.1:8765/health
```

### 写入一条项目决策事件

```bash
curl -X POST http://127.0.0.1:8765/api/v1/ingest \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "event_id": "demo-event-1",
    "event_type": "chat_message",
    "source_type": "feishu_chat",
    "occurred_at": "2026-04-27T00:00:00Z",
    "context": {"project_id": "project-demo"},
    "content_text": "我们决定采用方案 B 而不是方案 A，因为接入成本更低"
  }'
```

期望响应中包含：

```json
{
  "status": "ok",
  "stored": true,
  "memory_candidates": 1
}
```

### 检索刚写入的决策记忆

```bash
curl -X POST http://127.0.0.1:8765/api/v1/retrieve \
  -H 'Content-Type: application/json; charset=utf-8' \
  -d '{
    "query_text": "方案 B",
    "project_id": "project-demo",
    "top_k": 1,
    "include_trace": true
  }'
```

期望响应中 `results[0].domain` 为 `project_decision`。

## 主要 API

- `GET /health`：检查服务和本地存储状态。
- `POST /api/v1/ingest`：写入事件，并对项目决策类事件生成长期记忆。
- `POST /api/v1/retrieve`：检索长期记忆。
- `POST /api/v1/memories/search`：检索别名。
- `POST /api/v1/update`：更新记忆状态或分数。
- `POST /api/v1/memories/update`：更新别名。
- `GET /api/v1/proactive`：返回主动推送建议，当前已接入 team_retention 复习提醒。
- `POST /api/v1/benchmark/run`、`GET /api/v1/benchmark/{run_id}`：评测 API 骨架。

## 常用环境变量

- `LARKMEMORY_HOST`：服务监听地址，默认 `127.0.0.1`。
- `LARKMEMORY_PORT`：服务端口，默认 `8765`。
- `LARKMEMORY_SQLITE_PATH`：SQLite 数据库路径，默认 `.larkmemory/larkmemory.db`。
- `LARKMEMORY_ENABLE_LLM`：是否启用 LLM，默认 `false`。
- `LARKMEMORY_LLM_API_KEY`、`LARKMEMORY_LLM_MODEL`、`LARKMEMORY_LLM_BASE_URL`：LLM 配置，当前可选。
- `LARKMEMORY_ENABLE_EMBEDDING`：是否启用 embedding store，默认 `false`。
- `LARKMEMORY_LOG_LEVEL`：日志级别，默认 `INFO`。

## 当前注意事项

- `project_decision` 支持规则抽取和可选 LLM 抽取双路径。
- `/api/v1/retrieve` 当前走 `MemoryCore` fallback 召回，领域专用 retriever 已实现但尚未并入统一检索编排。
- `/api/v1/proactive` 已接入 team_retention 复习提醒主动推送。
