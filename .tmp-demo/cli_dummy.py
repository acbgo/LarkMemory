from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def build_parser() -> argparse.ArgumentParser:
    """Build a no-op CLI parser used to exercise LarkMemory command learning."""
    parser = argparse.ArgumentParser(
        prog="cli_dummy.py",
        description="No-op command for testing CLI workflow memory.",
    )
    parser.add_argument("--env", default="dev", help="Target environment.")
    parser.add_argument("--region", default="cn-north", help="Deployment region.")
    parser.add_argument("--canary", type=int, default=0, help="Canary percentage.")
    parser.add_argument("--tenant", default="demo", help="Tenant or customer key.")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout seconds.")
    parser.add_argument("--retries", type=int, default=1, help="Retry count.")
    parser.add_argument("--dry-run", action="store_true", help="Only validate inputs.")
    parser.add_argument("--feature-flag", default="", help="Optional feature flag.")
    return parser


def main() -> None:
    """Parse arguments and print them without performing any side effects."""
    args = build_parser().parse_args()
    payload = {
        "status": "ok",
        "message": "dummy command received; no external action performed",
        "received_at": datetime.now(timezone.utc).isoformat(),
        "args": vars(args),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
