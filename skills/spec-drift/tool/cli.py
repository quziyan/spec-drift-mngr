"""Command-line entry point for spec_drift.

Usage: python3 <skill-dir>/tool <command> [arguments]
(running the directory as a package, python3 -m <package> <command> [arguments], works too)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

import cmd_changed
import cmd_check
import cmd_impact
import cmd_inventory
import cmd_uncovered
import cmd_write
import repo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec_drift",
        description="Spec-drift checker: keeps the business-rule ledger pinned to the code",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="judge every entry's state and compare fingerprints")
    sub.add_parser("uncovered", help="symbols in the hot zone that no ledger entry covers")
    inventory_parser = sub.add_parser(
        "inventory",
        help="take stock of the eight AST element kinds of a symbol, to scaffold a ledger for existing code",
    )
    inv_group = inventory_parser.add_mutually_exclusive_group()
    inv_group.add_argument("--symbol", help="take stock of a single symbol only (file.py::name)")
    inv_group.add_argument("--file", help="take stock of every top-level symbol and class method in that file (relative to code_root)")
    impact_parser = sub.add_parser("impact", help="who references this symbol, plus the sibling anchors of the same entry")
    impact_parser.add_argument("target", help="a symbol (file.py::name) or an entry ID (R-XXX-000)")
    for name in ("sync", "confirm", "relink"):
        sp = sub.add_parser(name, help=f"{name} a single entry")
        sp.add_argument("entry_id")
        sp.add_argument("--by", required=True)
        sp.add_argument("--note", required=True)
        if name == "relink":
            sp.add_argument("--delete", action="store_true")
    changed_parser = sub.add_parser(
        "changed",
        help="symbols actually changed in this cycle (non-merge commits and merge commits)",
    )
    changed_parser.add_argument("--predict", required=True, help="prediction file path, relative to the repository root")
    return parser


CONFIG_ERROR_EXIT = 2


def main(argv: list[str] | None = None) -> int:
    """Exit codes: each command's own (0/1, see README); 2 when the tool could not even
    start — a missing or malformed `.spec-drift.json`, an ambiguous multi-value code_root,
    a ledger file that does not exist or does not parse. Those are the user's
    configuration errors, so they are reported as one `❌` line on stderr, never as a
    traceback (a traceback reads as "the tool crashed", and hides the fix the message
    already names).
    """
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return CONFIG_ERROR_EXIT


def _dispatch(args) -> int:
    ctx = repo.build_ctx()
    if args.command == "check":
        return cmd_check.run(ctx)
    if args.command == "uncovered":
        return cmd_uncovered.run(ctx)
    if args.command == "inventory":
        return cmd_inventory.run(ctx, symbol=args.symbol, file=args.file)
    if args.command == "impact":
        return cmd_impact.run(ctx, args.target)
    if args.command == "changed":
        return cmd_changed.run(ctx, args.predict)
    if args.command in ("sync", "confirm", "relink"):
        return cmd_write.run(
            ctx, args.command, args.entry_id, args.by, args.note,
            getattr(args, "delete", False), date.today().isoformat(),
        )
    raise SystemExit(f"unimplemented command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
