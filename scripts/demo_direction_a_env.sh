#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p .tmp-demo

export PATH="$ROOT/.venv/Scripts:$PATH"
export LARKMEMORY_SQLITE_PATH="$ROOT/.tmp-demo/direction-a-demo.db"
export LARKMEMORY_CONFIG_FILE="$ROOT/.tmp-demo/missing.env"
export LARKMEMORY_API_BASE="http://127.0.0.1:8765"

cat > .tmp-demo/cli_dummy.py <<'PY'
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--env")
parser.add_argument("--region")
parser.add_argument("--canary")
parser.add_argument("--tenant")
parser.add_argument("--timeout")
parser.add_argument("--retries")
parser.add_argument("--feature-flag")
args = parser.parse_args()

print("demo command received:", args)
PY

echo "Demo env ready."
echo "ROOT=$ROOT"
echo "LARKMEMORY_SQLITE_PATH=$LARKMEMORY_SQLITE_PATH"
echo "LARKMEMORY_API_BASE=$LARKMEMORY_API_BASE"
