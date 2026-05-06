#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source scripts/demo_direction_a_env.sh

echo "Starting LarkMemory API on http://127.0.0.1:8765"
python -m uvicorn src.app.main:app --host 127.0.0.1 --port 8765
