#!/usr/bin/env bash
set -euo pipefail

MANAGED_START="# >>> LarkMemory managed config >>>"
MANAGED_END="# <<< LarkMemory managed config <<<"
HOOK_START="# >>> LarkMemory hook >>>"
HOOK_END="# <<< LarkMemory hook <<<"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BASHRC="${HOME}/.bashrc"
API_BASE="${LARKMEMORY_API_BASE:-http://127.0.0.1:8765}"

mkdir -p "$(dirname "${BASHRC}")"
touch "${BASHRC}"

python - "$BASHRC" "$MANAGED_START" "$MANAGED_END" "$HOOK_START" "$HOOK_END" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

bashrc = Path(sys.argv[1])
managed_start, managed_end, hook_start, hook_end = sys.argv[2:6]
text = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""

for start, end in ((managed_start, managed_end), (hook_start, hook_end)):
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    text = pattern.sub("", text)

bashrc.write_text(text.rstrip() + ("\n" if text.strip() else ""), encoding="utf-8")
PY

cat >> "${BASHRC}" <<EOF

${MANAGED_START}
export LARKMEMORY_API_BASE="${API_BASE}"
export PATH="${PROJECT_ROOT}/.venv/Scripts:${PROJECT_ROOT}/.venv/bin:\$PATH"

lark-memory() {
  (
    cd "${PROJECT_ROOT}" || exit 1
    python -m src.sources.cli.main "\$@"
  )
}
${MANAGED_END}
EOF

# Load the function in this process so hook install uses the current project code.
export LARKMEMORY_API_BASE="${API_BASE}"
export PATH="${PROJECT_ROOT}/.venv/Scripts:${PROJECT_ROOT}/.venv/bin:${PATH}"
lark-memory() {
  (
    cd "${PROJECT_ROOT}" || exit 1
    python -m src.sources.cli.main "$@"
  )
}

lark-memory hook install >/dev/null

cat <<EOF
LarkMemory bash setup complete.

Project root: ${PROJECT_ROOT}
Config file : ${BASHRC}
API base    : ${API_BASE}

Run now:
  source ~/.bashrc
  type lark-memory
  lark-memory hook status
EOF
