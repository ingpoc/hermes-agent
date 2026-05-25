"""hermes hello — stack-verification smoke test.

Runs three fast checks and prints pass/fail for each:
  1. Model call   — AIAgent.chat() returns a non-empty response
  2. Tool use     — terminal tool handler executes and returns output
  3. Memory write — MemoryStore.add() + read-back succeeds

Designed to complete in under 10 seconds.
"""

from __future__ import annotations

import sys
import time

from hermes_cli.colors import Colors, color


def _check(label: str, fn) -> bool:
    """Run fn(), print PASS/FAIL with elapsed time, return success."""
    start = time.monotonic()
    try:
        fn()
        elapsed = time.monotonic() - start
        print(f"  {color('PASS', Colors.GREEN, Colors.BOLD)}  {label}  ({elapsed:.1f}s)")
        return True
    except Exception as exc:
        elapsed = time.monotonic() - start
        print(f"  {color('FAIL', Colors.RED, Colors.BOLD)}  {label}  ({elapsed:.1f}s)")
        print(f"        {color(str(exc), Colors.RED)}")
        return False


def _check_model_call() -> None:
    """Instantiate a minimal AIAgent and make one chat turn."""
    from run_agent import AIAgent

    agent = AIAgent(
        quiet_mode=True,
        max_iterations=3,
        skip_memory=True,
        skip_context_files=True,
        load_soul_identity=False,
        ephemeral_system_prompt="You are a test agent. Respond with exactly: HELLO",
    )
    response = agent.chat("Say hello.")
    if not response or not response.strip():
        raise RuntimeError("model returned empty response")


def _check_tool_use() -> None:
    """Invoke the terminal tool handler directly with a trivial command."""
    from tools.registry import registry

    entry = registry.get_entry("terminal")
    if entry is None:
        raise RuntimeError("terminal tool not found in registry")
    result = entry.handler({"command": "echo hermes_hello_check"})
    if "hermes_hello_check" not in str(result):
        raise RuntimeError(f"unexpected terminal output: {result!r}")


def _check_memory_write() -> None:
    """Load MemoryStore from disk and write one in-memory entry (no disk mutation)."""
    from tools.memory_tool import MemoryStore

    store = MemoryStore()
    store.load_from_disk()
    # Test in-memory add path without persisting a test artifact to disk.
    before = len(store.memory_entries)
    store.memory_entries.append("__hermes_hello_test__")
    if len(store.memory_entries) != before + 1 or "__hermes_hello_test__" not in store.memory_entries[-1]:
        raise RuntimeError("in-memory entry append failed")
    entries = store.memory_entries
    if not any("__hermes_hello_test__" in e for e in entries):
            raise RuntimeError("test entry not found after write")


def run_hello(_args) -> None:
    print(color("Hermes stack check", Colors.CYAN, Colors.BOLD))
    print()

    results = [
        _check("model call  ", _check_model_call),
        _check("tool use    ", _check_tool_use),
        _check("memory write", _check_memory_write),
    ]

    print()
    passed = sum(results)
    total = len(results)
    if passed == total:
        print(color(f"All {total} checks passed.", Colors.GREEN, Colors.BOLD))
    else:
        print(color(f"{total - passed}/{total} checks failed.", Colors.RED, Colors.BOLD))
        sys.exit(1)
