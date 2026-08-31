"""Command-line entry point for the repository's reproducible analysis tools."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Sequence


def package_version() -> str:
    try:
        return version("open-us-law-coverage")
    except PackageNotFoundError:
        return "0+unknown"


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if raw_args and raw_args[0] == "ca-probe":
        from .ca_probe import main as ca_probe_main

        ca_probe_main(raw_args[1:])
        return 0
    if raw_args and raw_args[0] == "identity-manifest":
        from .identity_manifest import main as identity_manifest_main

        identity_manifest_main(raw_args[1:])
        return 0

    parser = argparse.ArgumentParser(
        prog="open-us-law-coverage",
        description="Reproducible Open US Law coverage and identity audits.",
    )
    parser.add_argument("--version", action="version", version=package_version())
    parser.add_argument(
        "command",
        nargs="?",
        choices=("ca-probe", "identity-manifest"),
        help="ca-probe or identity-manifest (append --help for command options)",
    )
    parser.parse_args(raw_args)
    parser.print_help()
    return 0
