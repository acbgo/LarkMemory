"""Demo seed script — 快速注入测试命令到 Memory Engine，无需等慢速 hook。"""
from __future__ import annotations

import os
import sys
import time
import urllib.request
import json

API = os.environ.get("LARKMEMORY_API_BASE", "http://127.0.0.1:8765")
USER = "demo_user"
CWD = os.getcwd()

# ── 模拟 20 条 Shell 命令 ──
COMMANDS = [
    # pytest 命令（多次执行 + 不同参数，测试频率排序和参数记忆）
    "pytest tests/unit/core/test_service.py -q -p no:cacheprovider",
    "pytest tests/unit/core/test_service.py -q -p no:cacheprovider",
    "pytest tests/unit/core/test_service.py -q -p no:cacheprovider --tb=short",
    "pytest tests/unit/domains/cli_workflow -v --tb=short",
    "pytest tests/unit/domains/cli_workflow -v --tb=short",
    "pytest tests/unit/domains/cli_workflow -v --tb=long --maxfail=3",
    "pytest tests -x --maxfail=5",

    # git 命令（多次，测试高频命令排序）
    "git push origin main",
    "git push origin main",
    "git push origin main --force",
    "git pull --rebase origin main",
    "git status",

    # docker（单次 + 复杂参数）
    "docker build -t myapp:v2 . --build-arg ENV=prod",
    "docker run -d -p 8080:80 --name web myapp:v2",

    # npm / node
    "npm install --save react react-dom",
    "npm run build -- --mode production",

    # python 脚本
    "python train.py --lr 0.001 --epochs 100 --batch_size 32 --model resnet50",
    "python evaluate.py --checkpoint best.pt --dataset test --output results.json",
]


def post_ingest(payload: dict) -> bool:
    url = f"{API.rstrip('/')}/api/v1/ingest"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=3)
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main():
    # 1. 健康检查
    try:
        resp = urllib.request.urlopen(f"{API}/health", timeout=3)
        print(f"Backend: {resp.read().decode()[:80]}")
    except Exception:
        print("ERROR: 后端未启动，请先执行: uvicorn src.app.main:create_app --factory --port 8765 --reload")
        sys.exit(1)

    print(f"\n注入 {len(COMMANDS)} 条命令...")
    ok = 0
    for cmd in COMMANDS:
        payload = {
            "event_type": "command_finished",
            "source_type": "shell",
            "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "context": {"user_id": USER, "scope": "user"},
            "content_text": cmd,
            "payload": {"command": cmd.split()[0], "args": cmd.split()[1:], "exit_code": 0, "cwd": CWD},
            "tags": ["demo"],
        }
        if post_ingest(payload):
            ok += 1
            print(f"  [{ok:2d}/{len(COMMANDS)}] {cmd[:60]}")

    time.sleep(1.5)  # 等 memory engine 处理完

    # 2. 检索验证
    print("\n=== lark-memory suggest pytest ===")
    payload = {
        "query_text": "pytest",
        "user_id": USER,
        "top_k": 3,
    }
    req = urllib.request.Request(
        f"{API.rstrip('/')}/api/v1/retrieve",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
    for r in resp.get("results", []):
        print(f"  [{r['rank']}] {r['summary_text'][:80]}")

    print(f"\n=== lark-memory suggest git ===")
    payload["query_text"] = "git"
    req = urllib.request.Request(
        f"{API.rstrip('/')}/api/v1/retrieve",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
    for r in resp.get("results", []):
        print(f"  [{r['rank']}] {r['summary_text'][:80]}")

    print(f"\n=== lark-memory suggest docker ===")
    payload["query_text"] = "docker"
    req = urllib.request.Request(
        f"{API.rstrip('/')}/api/v1/retrieve",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
    for r in resp.get("results", []):
        print(f"  [{r['rank']}] {r['summary_text'][:80]}")

    print(f"\nDone. {ok}/{len(COMMANDS)} commands ingested.")
    print("现在可以在终端运行: lark-memory suggest pytest")
    print("或在终端运行: lark-memory suggest git")


if __name__ == "__main__":
    main()
