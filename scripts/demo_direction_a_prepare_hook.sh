#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source scripts/demo_direction_a_env.sh

rm -f "$LARKMEMORY_SQLITE_PATH"

lark-memory hook install

echo
echo "Hook installed. Run this in the current terminal before demo commands:"
echo "source ~/.bashrc"
echo
echo "Then check:"
echo "lark-memory hook status"
