from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _cmd_hook(args: argparse.Namespace) -> None:
    from src.sources.cli.hook import detect_shell, install, is_installed, uninstall

    shell = detect_shell()

    if args.action == "install":
        if is_installed(shell):
            print(f"hook already installed for {shell}, reinstalling...")
        _ok, msg = install(shell)
        print(msg)
        print(f"shell hook installed. restart your shell or run: source ~/.{shell}rc")
    elif args.action == "uninstall":
        _ok, msg = uninstall(shell)
        print(msg)
    elif args.action == "status":
        if is_installed(shell):
            print(f"hook is installed for {shell}")
        else:
            print(f"hook is NOT installed for {shell}")


def _cmd_suggest(args: argparse.Namespace) -> None:
    from src.sources.cli.retrieve import run_suggest

    output = run_suggest(
        args.query or "",
        project_id=args.project,
        command=args.command,
        cwd=os.getcwd(),
    )
    print(output)


def _cmd_complete(args: argparse.Namespace) -> None:
    from src.sources.cli.retrieve import run_complete

    output = run_complete(args.line, args.cur, cwd=os.getcwd())
    if output:
        print(output)


def _cmd_completion(args: argparse.Namespace) -> None:
    from src.sources.cli.completion import get_completion_script

    print(get_completion_script(args.shell))


def _cmd_ingest(args: argparse.Namespace) -> None:
    from src.sources.cli.ingest import run_from_args

    run_from_args(vars(args))


def _fill_complete_args(args: argparse.Namespace) -> None:
    """Normalize shell completion positional args, ignoring argparse's `--` separator."""
    if not args.remainder or args.line:
        return
    remainder = list(args.remainder)
    if remainder and remainder[0] == "--":
        remainder = remainder[1:]
    if len(remainder) >= 1:
        args.line = remainder[0]
    if len(remainder) >= 2:
        args.cur = remainder[1]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lark-memory",
        description="LarkMemory CLI - command workflow memory",
    )
    sub = parser.add_subparsers(dest="subcommand")

    hook_parser = sub.add_parser("hook", help="install/uninstall shell hooks")
    hook_parser.add_argument(
        "action",
        choices=["install", "uninstall", "status"],
        help="install, uninstall, or check hook status",
    )

    suggest_parser = sub.add_parser("suggest", help="query command memories")
    suggest_parser.add_argument("query", nargs="?", default="", help="search query text")
    suggest_parser.add_argument("--project", default=None, help="filter by project")
    suggest_parser.add_argument("--command", default=None, help="filter by command name")

    complete_parser = sub.add_parser("complete", help="tab completion (called by shell)")
    complete_parser.add_argument("--line", default="", help="full command line")
    complete_parser.add_argument("--cur", default="", help="current word")
    complete_parser.add_argument("remainder", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    completion_parser = sub.add_parser("completion", help="output shell completion script")
    completion_parser.add_argument("shell", choices=["bash", "zsh"], help="shell type")

    ingest_parser = sub.add_parser("ingest", help="internal: report command execution")
    ingest_parser.add_argument("--command", default="", help="executed command text")
    ingest_parser.add_argument("--exit-code", type=int, default=0, help="command exit code")
    ingest_parser.add_argument("--cwd", default="", help="working directory")
    ingest_parser.add_argument("--duration", type=int, default=0, help="execution duration ms")

    args = parser.parse_args(argv)

    if args.subcommand == "hook":
        _cmd_hook(args)
    elif args.subcommand == "suggest":
        _cmd_suggest(args)
    elif args.subcommand == "complete":
        _fill_complete_args(args)
        _cmd_complete(args)
    elif args.subcommand == "completion":
        _cmd_completion(args)
    elif args.subcommand == "ingest":
        _cmd_ingest(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
