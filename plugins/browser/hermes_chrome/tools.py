"""Hermes-owned Chrome browser-control tool."""

from __future__ import annotations

import json
import os
import platform
import socket
import stat
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from tools.registry import tool_error, tool_result

PLUGIN_DIR = Path(__file__).resolve().parent
DEFAULT_TIMEOUT_SECONDS = 45
MAX_ACTIONS = 20
MAX_TEXT_CHARS = 120_000


def _runtime_root() -> Path:
    return get_hermes_home() / "chrome-bridge"


def _runtime_extension_dir() -> Path:
    return _runtime_root() / "extension"


def _runtime_native_host() -> Path:
    return _runtime_root() / "native" / "native_host.py"


def _hermes_extension_socket() -> Path:
    return Path(os.environ.get("HERMES_CHROME_BRIDGE_SOCKET", get_hermes_home() / "run" / "chrome-bridge.sock"))


def _check_hermes_chrome_available() -> bool:
    return (
        (_runtime_extension_dir() / "manifest.json").exists()
        and (_runtime_extension_dir() / "service_worker.js").exists()
        and (PLUGIN_DIR / "native" / "native_host.py").exists()
    )


def _native_manifest_dir() -> Path | None:
    system = platform.system().lower()
    home = Path.home()
    if system == "darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"
    if system == "linux":
        return home / ".config" / "google-chrome" / "NativeMessagingHosts"
    return None


def _coerce_positive_int(raw: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _normalise_action(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    action_type = str(raw.get("type") or "").strip()
    if not action_type:
        return None
    action = dict(raw)
    action["type"] = action_type
    return action


def _normalise_actions(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("actions must be a list")
    actions: list[dict[str, Any]] = []
    for item in raw[:MAX_ACTIONS]:
        action = _normalise_action(item)
        if action is not None:
            actions.append(action)
    return actions


def _install_info() -> dict[str, Any]:
    manifest_dir = _native_manifest_dir()
    manifest_path = manifest_dir / "com.hermes.chrome_bridge.json" if manifest_dir else None
    return {
        "success": True,
        "extension_dir": str(_runtime_extension_dir()),
        "native_host": str(_runtime_native_host()),
        "native_manifest_path": str(manifest_path) if manifest_path else None,
        "socket": str(_hermes_extension_socket()),
        "install_command": (
            f"{PLUGIN_DIR / 'scripts' / 'install_hermes_chrome_bridge.py'} "
            "--install-runtime"
        ),
        "manifest_command": (
            f"{PLUGIN_DIR / 'scripts' / 'install_hermes_chrome_bridge.py'} "
            "--install-runtime --extension-id <chrome-extension-id>"
        ),
        "steps": [
            "Run install_command to copy the Hermes Chrome Bridge runtime into HERMES_HOME.",
            "Open chrome://extensions and enable Developer mode.",
            f"Load unpacked extension from {_runtime_extension_dir()}.",
            "Copy the loaded extension id.",
            "Run manifest_command with that extension id.",
            "Reload the Hermes Chrome Bridge extension and call hermes_chrome_browser status.",
        ],
    }


def _read_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except Exception as exc:
        return None, str(exc)


def _extension_manifest_info() -> dict[str, Any]:
    manifest_path = _runtime_extension_dir() / "manifest.json"
    manifest, error = _read_json_file(manifest_path)
    if manifest is None:
        return {"path": str(manifest_path), "exists": manifest_path.exists(), "valid_json": False, "error": error}
    background = manifest.get("background") if isinstance(manifest.get("background"), dict) else {}
    resources = manifest.get("web_accessible_resources")
    resource_names: list[str] = []
    if isinstance(resources, list):
        for item in resources:
            if isinstance(item, dict) and isinstance(item.get("resources"), list):
                resource_names.extend(str(resource) for resource in item["resources"])
    return {
        "path": str(manifest_path),
        "exists": True,
        "valid_json": True,
        "name": manifest.get("name"),
        "manifest_version": manifest.get("manifest_version"),
        "service_worker": background.get("service_worker"),
        "has_cursor_asset": "images/pointer-shape-animated.svg" in resource_names,
        "has_scripting_permission": "scripting" in (manifest.get("permissions") or []),
        "has_native_messaging_permission": "nativeMessaging" in (manifest.get("permissions") or []),
    }


def _native_manifest_info() -> dict[str, Any]:
    manifest_dir = _native_manifest_dir()
    manifest_path = manifest_dir / "com.hermes.chrome_bridge.json" if manifest_dir else None
    if manifest_path is None:
        return {"path": None, "exists": False, "valid_json": False, "error": f"Unsupported platform: {platform.system()}"}
    manifest, error = _read_json_file(manifest_path)
    if manifest is None:
        return {"path": str(manifest_path), "exists": manifest_path.exists(), "valid_json": False, "error": error}
    allowed_origins = manifest.get("allowed_origins") if isinstance(manifest.get("allowed_origins"), list) else []
    host_path = Path(str(manifest.get("path") or "")).expanduser()
    expected_host = _runtime_native_host()
    return {
        "path": str(manifest_path),
        "exists": True,
        "valid_json": True,
        "name": manifest.get("name"),
        "host_path": str(host_path) if str(host_path) else "",
        "host_exists": host_path.exists(),
        "host_matches_runtime": host_path == expected_host,
        "allowed_origins": allowed_origins,
        "allowed_extension_ids": [
            origin.removeprefix("chrome-extension://").removesuffix("/")
            for origin in allowed_origins
            if isinstance(origin, str) and origin.startswith("chrome-extension://")
        ],
    }


def _socket_info() -> dict[str, Any]:
    socket_path = _hermes_extension_socket()
    info: dict[str, Any] = {"path": str(socket_path), "exists": socket_path.exists()}
    if not socket_path.exists():
        return info
    try:
        mode = socket_path.stat().st_mode
    except OSError as exc:
        info["stat_error"] = str(exc)
        return info
    info["is_socket"] = stat.S_ISSOCK(mode)
    if not info["is_socket"]:
        info["stale_reason"] = "Path exists but is not a Unix socket"
    return info


def _diagnostics() -> dict[str, Any]:
    extension_manifest = _extension_manifest_info()
    native_manifest = _native_manifest_info()
    native_host = _runtime_native_host()
    socket_info = _socket_info()
    checks = {
        "runtime_extension_manifest": bool(extension_manifest.get("exists") and extension_manifest.get("valid_json")),
        "runtime_service_worker": (_runtime_extension_dir() / "service_worker.js").exists(),
        "runtime_native_host": native_host.exists(),
        "runtime_native_host_executable": native_host.exists() and os.access(native_host, os.X_OK),
        "chrome_native_manifest": bool(native_manifest.get("exists") and native_manifest.get("valid_json")),
        "native_manifest_host_matches_runtime": bool(native_manifest.get("host_matches_runtime")),
        "native_manifest_has_allowed_extension": bool(native_manifest.get("allowed_extension_ids")),
        "socket_path_is_clean_or_live": not socket_info.get("exists") or bool(socket_info.get("is_socket")),
    }
    blocking = [name for name, passed in checks.items() if not passed]
    return {
        "success": True,
        "preflight_ok": not blocking,
        "blocking_checks": blocking,
        "checks": checks,
        "hermes_home": str(get_hermes_home()),
        "extension_dir": str(_runtime_extension_dir()),
        "native_host": str(native_host),
        "extension_manifest": extension_manifest,
        "native_manifest": native_manifest,
        "socket": socket_info,
    }


def _preflight() -> dict[str, Any]:
    socket_path = _hermes_extension_socket()
    manifest_dir = _native_manifest_dir()
    manifest_path = manifest_dir / "com.hermes.chrome_bridge.json" if manifest_dir else None
    diagnostics = _diagnostics()
    return {
        "success": True,
        "extension_dir": str(_runtime_extension_dir()),
        "extension_manifest": (_runtime_extension_dir() / "manifest.json").exists(),
        "service_worker": (_runtime_extension_dir() / "service_worker.js").exists(),
        "native_host": _runtime_native_host().exists(),
        "native_manifest_path": str(manifest_path) if manifest_path else None,
        "native_manifest": manifest_path.exists() if manifest_path else False,
        "socket": str(socket_path),
        "socket_exists": socket_path.exists(),
        "hermes_home": str(get_hermes_home()),
        "diagnostics": diagnostics,
        "preflight_ok": diagnostics["preflight_ok"],
        "blocking_checks": diagnostics["blocking_checks"],
    }


def _build_bridge_request(args: dict[str, Any], *, task_id: str | None) -> dict[str, Any]:
    action = str(args.get("action") or "run").strip().lower()
    if action not in {"install_info", "preflight", "diagnose", "health", "status", "run"}:
        raise ValueError("action must be one of: install_info, preflight, diagnose, health, status, run")

    request: dict[str, Any] = {
        "action": action,
        "sessionName": str(args.get("session_name") or "Hermes Chrome"),
        "taskId": task_id or "",
        "maxTextChars": _coerce_positive_int(
            args.get("max_text_chars"),
            default=20_000,
            minimum=1_000,
            maximum=MAX_TEXT_CHARS,
        ),
    }
    if action == "run":
        actions = _normalise_actions(args.get("actions"))
        url = str(args.get("url") or "").strip()
        if url:
            actions.insert(0, {"type": "goto", "url": url})
        if not actions:
            actions = [{"type": "snapshot"}]
        request["actions"] = actions
        request["useSelectedTab"] = bool(args.get("use_selected_tab", False))
    return request


def _build_extension_request(request: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    if request["action"] == "status":
        return {"type": "status", "timeoutSeconds": timeout_seconds}
    return {
        "type": "run",
        "actions": request.get("actions", []),
        "timeoutSeconds": timeout_seconds,
        "sessionName": request.get("sessionName"),
        "taskId": request.get("taskId"),
        "useSelectedTab": request.get("useSelectedTab", False),
        "maxTextChars": request.get("maxTextChars", 20_000),
    }


def _run_extension_bridge(request: dict[str, Any], *, timeout_seconds: int) -> dict[str, Any]:
    socket_path = _hermes_extension_socket()
    if not socket_path.exists():
        return {
            "success": False,
            "error": (
                "Hermes Chrome Bridge socket is not available. Install the Hermes Chrome "
                "extension and native host, then reload Chrome."
            ),
            "socket": str(socket_path),
        }
    payload = _build_extension_request(request, timeout_seconds=timeout_seconds)
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout_seconds)
        with client:
            client.connect(str(socket_path))
            client.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        raw = b"".join(chunks).decode("utf-8")
        return json.loads(raw) if raw else {"success": False, "error": "Hermes extension bridge returned no output"}
    except Exception as exc:
        return {"success": False, "error": f"Hermes extension bridge failed: {exc}", "socket": str(socket_path)}


def _health_check(*, timeout_seconds: int) -> dict[str, Any]:
    diagnostics = _diagnostics()
    result: dict[str, Any] = {
        "success": True,
        "preflight_ok": diagnostics["preflight_ok"],
        "blocking_checks": diagnostics["blocking_checks"],
        "diagnostics": diagnostics,
        "bridge_status": None,
        "selected_tab_ready": False,
        "ready": False,
    }
    if not diagnostics["preflight_ok"]:
        return result
    bridge_status = _run_extension_bridge({"action": "status"}, timeout_seconds=timeout_seconds)
    result["bridge_status"] = bridge_status
    result["ready"] = bool(bridge_status.get("success"))
    result["selected_tab_ready"] = bool(bridge_status.get("content_script", {}).get("injected"))
    if not bridge_status.get("success"):
        result["bridge_error"] = bridge_status.get("error") or "Hermes Chrome bridge status failed"
    return result


HERMES_CHROME_BROWSER_SCHEMA = {
    "name": "hermes_chrome_browser",
    "description": (
        "Control the user's signed-in Chrome profile through the Hermes Chrome "
        "extension and native messaging host. Use for browser testing or authenticated "
        "browser tasks when the user explicitly wants Chrome state."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["install_info", "preflight", "diagnose", "health", "status", "run"],
                "description": (
                    "Use install_info for setup instructions, preflight for local checks, "
                    "diagnose for detailed deterministic runtime checks, status to check "
                    "live bridge availability, health for combined diagnostics plus live "
                    "status, and run to execute browser actions."
                ),
                "default": "run",
            },
            "url": {
                "type": "string",
                "description": "Optional URL to open before executing actions.",
            },
            "session_name": {
                "type": "string",
                "description": "Short Chrome session name for this task.",
            },
            "use_selected_tab": {
                "type": "boolean",
                "description": "Reuse Chrome's selected tab instead of creating a managed tab.",
                "default": False,
            },
            "actions": {
                "type": "array",
                "description": (
                    "Ordered browser actions. Supported types: goto, wait, snapshot, text, "
                    "screenshot, click_text, fill_selector, click_selector, cursor_move, "
                    "cursor_click, cursor_right_click, cursor_double_click, cursor_triple_click, "
                    "cursor_type, cursor_key, cursor_drag, cursor_scroll, cursor_status, "
                    "cursor_hide, evaluate, close_tab. High-level click/fill actions animate "
                    "the visible Hermes cursor before interacting."
                ),
                "items": {"type": "object"},
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum wall time for the bridge request.",
                "default": DEFAULT_TIMEOUT_SECONDS,
            },
            "max_text_chars": {
                "type": "integer",
                "description": "Maximum text or DOM snapshot characters returned per action.",
                "default": 20000,
            },
        },
        "additionalProperties": False,
    },
}


def _handle_hermes_chrome_browser(args: dict, task_id: str | None = None, **_: Any) -> str:
    try:
        args = args or {}
        request = _build_bridge_request(args, task_id=task_id)
        timeout_seconds = _coerce_positive_int(
            args.get("timeout_seconds"),
            default=DEFAULT_TIMEOUT_SECONDS,
            minimum=5,
            maximum=180,
        )
    except Exception as exc:
        return tool_error(str(exc), success=False)

    if request["action"] == "install_info":
        return tool_result(_install_info())
    if request["action"] == "preflight":
        return tool_result(_preflight())
    if request["action"] == "diagnose":
        return tool_result(_diagnostics())
    if request["action"] == "health":
        return tool_result(_health_check(timeout_seconds=timeout_seconds))

    result = _run_extension_bridge(request, timeout_seconds=timeout_seconds)
    if not result.get("success"):
        return tool_error(result.get("error") or "Hermes Chrome bridge failed", success=False, details=result)
    return tool_result(result)
