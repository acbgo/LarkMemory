from __future__ import annotations

import argparse
import json


def main() -> None:
    """Demo-only CLI target: parse many params and print them without side effects."""
    parser = argparse.ArgumentParser(description="LarkMemory direction A demo command")
    parser.add_argument("--env", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--canary", default="")
    parser.add_argument("--tenant", default="")
    parser.add_argument("--timeout", default="")
    parser.add_argument("--retries", default="")
    parser.add_argument("--feature-flag", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    print(json.dumps(vars(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
