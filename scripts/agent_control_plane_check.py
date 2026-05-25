#!/usr/bin/env python3
"""Offline self-audit checks for Hermes agent-control-plane work.

The goal is deliberately modest: catch missing safety documentation and make
control-plane branches carry a runnable, credential-free verification step before
runtime behavior changes begin.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_DOC = Path("docs/agent-control-plane-operating-model.md")
REQUIRED_PHRASES = [
    "Do not develop directly inside a user's active working copy.",
    "/Users/gurusharan/Documents/Hermes-Agent-Workspace/repos/hermes-agent-ingpoc",
    "Push the branch to the user's fork or staging remote.",
    "Do not save secrets in repository files.",
]


def _repo_root(start: Path) -> Path:
    for path in [start, *start.parents]:
        if (path / ".git").exists() and (path / "pyproject.toml").exists():
            return path
    raise RuntimeError(f"could not find repository root from {start}")


def run(root: Path) -> list[str]:
    failures: list[str] = []
    doc = root / REQUIRED_DOC
    if not doc.exists():
        return [f"missing required operating-model doc: {REQUIRED_DOC}"]

    text = doc.read_text(encoding="utf-8")
    for phrase in REQUIRED_PHRASES:
        if phrase not in text:
            failures.append(f"{REQUIRED_DOC} is missing required phrase: {phrase!r}")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to check; defaults to discovering from cwd.",
    )
    args = parser.parse_args(argv)

    try:
        root = args.repo_root.resolve() if args.repo_root else _repo_root(Path.cwd().resolve())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    failures = run(root)
    if failures:
        print("Agent control-plane self-audit failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Agent control-plane self-audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
