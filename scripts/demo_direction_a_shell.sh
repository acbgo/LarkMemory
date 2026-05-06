#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source scripts/demo_direction_a_env.sh

echo
echo "1) Run normal shell commands. Bash hook records them automatically."
python .tmp-demo/cli_dummy.py --env staging --region cn-north --canary 10 --tenant demo-a --timeout 60 --retries 2
python .tmp-demo/cli_dummy.py --env staging --region cn-north --canary 10 --tenant demo-a --timeout 60 --retries 2
python .tmp-demo/cli_dummy.py --env prod --region cn-east --canary 5 --tenant demo-a --timeout 30 --retries 1 --feature-flag release-demo

sleep 1

echo
echo "2) Suggest reads local cli_command_pattern frequency, no LLM."
lark-memory suggest python

echo
echo "3) Complete returns frequent params for this script."
lark-memory complete -- "python .tmp-demo/cli_dummy.py " ""

echo
echo "4) Complete skips params already typed."
lark-memory complete -- "python .tmp-demo/cli_dummy.py --env staging " ""

echo
echo "5) Add a non-Python command and show command isolation."
git log --oneline --max-count 5 >/dev/null || true
git log --oneline --max-count 5 >/dev/null || true
sleep 1

echo
echo "6) Git suggestions stay with git."
lark-memory suggest git
lark-memory complete -- "git log " ""

echo
echo "7) Python completion is not polluted by git params."
lark-memory complete -- "python .tmp-demo/cli_dummy.py " ""
