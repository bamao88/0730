"""DocFit command-line entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="docfit")
    parser.add_argument("--version", action="version", version="docfit 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="check the local DocFit environment")
    doctor_parser.add_argument(
        "--require",
        choices=("agent-smoke", "provider"),
        dest="requirement",
    )
    doctor_parser.add_argument("--json", action="store_true", dest="as_json")

    smoke_parser = subparsers.add_parser(
        "agent-smoke",
        help="run one live Claude Agent SDK smoke case",
    )
    smoke_parser.add_argument(
        "--case",
        required=True,
        choices=("image", "ask-user", "denied-tools"),
        dest="case_name",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        from docfit.doctor import doctor_main

        return doctor_main(requirement=args.requirement, as_json=args.as_json)
    if args.command == "agent-smoke":
        from docfit.smoke import smoke_main

        return smoke_main(args.case_name)
    raise AssertionError(f"unhandled command: {args.command}")
