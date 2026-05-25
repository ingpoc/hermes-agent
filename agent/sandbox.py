"""OS-level sandbox wrapper for shell tool execution.

Wraps subprocess args with platform-appropriate sandboxing:
  - Linux:  bubblewrap (bwrap) — ``--unshare-net`` blocks outbound network
  - macOS:  sandbox-exec (Seatbelt) — ``(deny network*)`` blocks outbound network
  - Other:  bare passthrough (no-op)

Environment variables:
  HERMES_SANDBOX_DISABLED=1         — bypass all sandboxing (e.g. for CI)
  HERMES_SANDBOX_NETWORK_DISABLED=1 — block outbound network when sandbox is active

Usage::

    from agent.sandbox import wrap_in_sandbox, sandbox_status

    new_args = wrap_in_sandbox(["bash", "-c", "echo hi"])
    status = sandbox_status()  # {"available": True, "backend": "bwrap", ...}
"""

from __future__ import annotations

import logging
import shutil
import sys
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)
_warned_unavailable = False


def _warn_sandbox_unavailable() -> None:
    """Emit a one-time warning when the sandbox backend is absent but not disabled."""
    global _warned_unavailable
    if _warned_unavailable:
        return
    _warned_unavailable = True
    if sys.platform.startswith("linux"):
        hint = "Install with: sudo apt install bubblewrap"
    elif sys.platform == "darwin":
        hint = "sandbox-exec should be present on macOS — check PATH"
    else:
        hint = f"No sandbox backend for platform {sys.platform!r}"
    logger.warning(
        "Hermes sandbox backend unavailable — shell commands run with full user "
        "permissions. Set HERMES_SANDBOX_DISABLED=1 to suppress this warning. %s",
        hint,
    )


def _sandbox_disabled() -> bool:
    from hermes_constants import SANDBOX_DISABLED
    return SANDBOX_DISABLED


def _network_disabled() -> bool:
    from hermes_constants import SANDBOX_NETWORK_DISABLED
    return SANDBOX_NETWORK_DISABLED


def _bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def _sandbox_exec_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def _wrap_bwrap(args: List[str]) -> List[str]:
    """Wrap *args* with bubblewrap for Linux network isolation."""
    bwrap_cmd = ["bwrap",
                 "--bind", "/", "/",
                 "--dev-bind", "/dev", "/dev",
                 "--proc", "/proc",
                 "--tmpfs", "/tmp",
                 "--die-with-parent"]
    if _network_disabled():
        bwrap_cmd.append("--unshare-net")
    bwrap_cmd.append("--")
    return bwrap_cmd + args


_MACOS_SANDBOX_ALLOW_PROFILE = "(version 1)(allow default)"
_MACOS_SANDBOX_DENY_NET_PROFILE = "(version 1)(allow default)(deny network*)"


def _wrap_sandbox_exec(args: List[str]) -> List[str]:
    """Wrap *args* with macOS sandbox-exec for Seatbelt isolation."""
    profile = _MACOS_SANDBOX_DENY_NET_PROFILE if _network_disabled() else _MACOS_SANDBOX_ALLOW_PROFILE
    return ["sandbox-exec", "-p", profile, "--"] + args


def wrap_in_sandbox(
    args: List[str],
    env: Optional[Dict] = None,
    cwd: Optional[str] = None,
) -> List[str]:
    """Return *args* optionally wrapped with the appropriate OS sandbox.

    Falls back to the bare *args* when:
    - ``HERMES_SANDBOX_DISABLED=1``
    - the sandbox tool (bwrap / sandbox-exec) is not installed
    - the platform has no supported sandbox backend

    Args:
        args:  Command + arguments list, as passed to ``subprocess.Popen``.
        env:   Ignored (passed for API symmetry; sandbox does not alter env).
        cwd:   Ignored (Popen's cwd is respected by bwrap via bind mount).

    Returns:
        Possibly-wrapped args list.
    """
    if not args:
        return args
    if _sandbox_disabled():
        return args

    if sys.platform.startswith("linux") and _bwrap_available():
        return _wrap_bwrap(args)
    if sys.platform == "darwin" and _sandbox_exec_available():
        return _wrap_sandbox_exec(args)
    _warn_sandbox_unavailable()
    return args


def sandbox_status() -> Dict:
    """Return a status dict describing the active sandbox configuration."""
    disabled = _sandbox_disabled()
    network_blocked = _network_disabled()

    on_linux = sys.platform.startswith("linux")
    on_mac = sys.platform == "darwin"

    if disabled:
        return {
            "available": False,
            "backend": None,
            "active": False,
            "network_blocked": False,
            "reason": "HERMES_SANDBOX_DISABLED=1",
        }

    if on_linux and _bwrap_available():
        return {
            "available": True,
            "backend": "bwrap",
            "active": True,
            "network_blocked": network_blocked,
            "reason": None,
        }
    if on_mac and _sandbox_exec_available():
        return {
            "available": True,
            "backend": "sandbox-exec",
            "active": True,
            "network_blocked": network_blocked,
            "reason": None,
        }

    reasons = []
    if on_linux and not _bwrap_available():
        reasons.append("bwrap not installed")
    elif on_mac and not _sandbox_exec_available():
        reasons.append("sandbox-exec not found")
    elif not on_linux and not on_mac:
        reasons.append(f"no sandbox backend for platform {sys.platform!r}")

    return {
        "available": False,
        "backend": None,
        "active": False,
        "network_blocked": False,
        "reason": "; ".join(reasons) or "unsupported platform",
    }
