"""Deterministic quality-gate checks for agent-claimed facts.

Invoked via ``hermes quality-gate`` (CLI) or ``run_quality_gate()`` (programmatic).

Claim format::

    {"type": "file_exists",   "value": "/path/to/file"}
    {"type": "symbol_exists", "value": "def my_func", "search_dir": "."}
    {"type": "memory_fresh",  "value": "slug-or-keyword"}

Returns ``{"passed": bool, "failures": [...], "checks": [...]}`` where
each ``checks`` entry records the outcome of one claim.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def run_quality_gate(claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Verify a list of claims deterministically.

    Args:
        claims: List of claim dicts with ``type`` and ``value`` keys.

    Returns:
        Dict with ``passed`` bool, ``failures`` list, and ``checks`` list.
    """
    failures: List[str] = []
    checks: List[Dict[str, Any]] = []

    for claim in claims:
        claim_type = claim.get("type", "")
        value = claim.get("value", "")

        if claim_type == "file_exists":
            ok = Path(value).exists()
            checks.append({"type": claim_type, "value": value, "passed": ok})
            if not ok:
                failures.append(f"File not found: {value}")

        elif claim_type == "symbol_exists":
            search_dir = claim.get("search_dir", ".")
            pattern = value
            try:
                result = subprocess.run(
                    ["grep", "-r", "--include=*.py", "-l", pattern, search_dir],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                ok = result.returncode == 0 and bool(result.stdout.strip())
            except (subprocess.TimeoutExpired, FileNotFoundError):
                ok = False
            checks.append({"type": claim_type, "value": value, "search_dir": search_dir, "passed": ok})
            if not ok:
                failures.append(f"Symbol not found: {value!r} in {search_dir}")

        elif claim_type == "memory_fresh":
            from hermes_constants import get_hermes_home
            from tools.memory_tool import MEMORY_STALE_DAYS, _parse_written_at, ENTRY_DELIMITER

            mem_dir = get_hermes_home() / "memories"
            mem_path = mem_dir / "MEMORY.md"
            keyword = value.lower()
            found_fresh = False
            found_stale = False

            if mem_path.exists():
                try:
                    raw = mem_path.read_text(encoding="utf-8")
                    entries = [e.strip() for e in raw.split(ENTRY_DELIMITER) if e.strip()]
                    now = datetime.now(timezone.utc)
                    for entry in entries:
                        content, written_at = _parse_written_at(entry)
                        if keyword not in content.lower():
                            continue
                        if written_at is None:
                            found_fresh = True
                            break
                        days_old = (now - written_at).days
                        if days_old <= MEMORY_STALE_DAYS:
                            found_fresh = True
                        else:
                            found_stale = True
                except OSError:
                    pass

            if found_fresh:
                ok = True
            elif found_stale:
                ok = False
                failures.append(
                    f"Memory entry matching {value!r} exists but is stale (> {MEMORY_STALE_DAYS} days old)"
                )
            else:
                ok = False
                failures.append(f"No memory entry found matching: {value!r}")
            checks.append({"type": claim_type, "value": value, "passed": ok})

        else:
            checks.append({"type": claim_type, "value": value, "passed": False, "error": "unknown claim type"})
            failures.append(f"Unknown claim type: {claim_type!r}")

    return {"passed": len(failures) == 0, "failures": failures, "checks": checks}


def cmd_quality_gate_main(args) -> None:
    """Entry point for ``hermes quality-gate`` CLI subcommand."""
    if args.claims_file:
        try:
            with open(args.claims_file, encoding="utf-8") as f:
                claims = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading claims file: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.claim:
        claims = []
        for raw in args.claim:
            try:
                claims.append(json.loads(raw))
            except json.JSONDecodeError as e:
                print(f"Invalid claim JSON {raw!r}: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        print("No claims provided. Use --claim or --claims-file.", file=sys.stderr)
        sys.exit(1)

    result = run_quality_gate(claims)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_quality_gate_result(result)

    sys.exit(0 if result["passed"] else 2)


def _print_quality_gate_result(result: Dict[str, Any]) -> None:
    status = "PASSED" if result["passed"] else "FAILED"
    print(f"\nQuality gate: {status}")
    print(f"  {len(result['checks'])} check(s) run, {len(result['failures'])} failure(s)\n")
    for check in result["checks"]:
        icon = "✓" if check["passed"] else "✗"
        print(f"  {icon} [{check['type']}] {check['value']}")
    if result["failures"]:
        print("\nFailures:")
        for f in result["failures"]:
            print(f"  - {f}")
    print()
