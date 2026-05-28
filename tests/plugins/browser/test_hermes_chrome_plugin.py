from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

from plugins.browser.hermes_chrome import tools
from plugins.browser.hermes_chrome.native import native_host

INSTALLER = Path(__file__).resolve().parents[3] / "plugins" / "browser" / "hermes_chrome" / "scripts" / "install_hermes_chrome_bridge.py"


def test_build_status_request_is_hermes_only():
    request = tools._build_bridge_request({"action": "status"}, task_id="task-1")

    assert request["action"] == "status"
    assert request["taskId"] == "task-1"
    assert "pluginRoot" not in request


def test_build_run_request_prepends_url_and_limits_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    actions = [{"type": "snapshot"} for _ in range(tools.MAX_ACTIONS + 5)]
    request = tools._build_bridge_request(
        {"action": "run", "url": "https://example.com", "actions": actions},
        task_id="task-2",
    )

    assert request["action"] == "run"
    assert request["actions"][0] == {"type": "goto", "url": "https://example.com"}
    assert len(request["actions"]) == tools.MAX_ACTIONS + 1
    assert request["taskId"] == "task-2"


def test_build_run_request_rejects_non_list_actions():
    with pytest.raises(ValueError, match="actions must be a list"):
        tools._build_bridge_request({"action": "run", "actions": {"type": "snapshot"}}, task_id=None)


def test_install_info_reports_hermes_extension_paths():
    payload = tools._install_info()

    assert payload["success"] is True
    assert payload["extension_dir"].endswith("chrome-bridge/extension")
    assert payload["native_host"].endswith("chrome-bridge/native/native_host.py")
    assert payload["socket"].endswith("run/chrome-bridge.sock")
    assert payload["install_command"].endswith("--install-runtime")
    assert "--extension-id <chrome-extension-id>" in payload["manifest_command"]


def test_installer_writes_native_manifest_to_override_dir(tmp_path):
    native_host_path = tmp_path / "native_host.py"
    native_host_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    manifest_dir = tmp_path / "NativeMessagingHosts"

    proc = subprocess.run(
        [
            str(INSTALLER),
            "--extension-id",
            "abcdefghijklmnopabcdefghijklmnop",
            "--native-host",
            str(native_host_path),
            "--manifest-dir",
            str(manifest_dir),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    manifest_path = manifest_dir / "com.hermes.chrome_bridge.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["manifest_path"] == str(manifest_path)
    assert manifest["path"] == str(native_host_path.resolve())
    assert manifest["allowed_origins"] == ["chrome-extension://abcdefghijklmnopabcdefghijklmnop/"]


def test_preflight_reports_hermes_runtime(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes-home"
    extension_dir = hermes_home / "chrome-bridge" / "extension"
    native_dir = hermes_home / "chrome-bridge" / "native"
    extension_dir.mkdir(parents=True)
    native_dir.mkdir(parents=True)
    (extension_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (extension_dir / "service_worker.js").write_text("", encoding="utf-8")
    (native_dir / "native_host.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    socket_path = tmp_path / "chrome.sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_CHROME_BRIDGE_SOCKET", str(socket_path))
    monkeypatch.setattr(tools, "_native_manifest_dir", lambda: tmp_path / "missing-manifests")

    payload = tools._preflight()

    assert payload["extension_manifest"] is True
    assert payload["service_worker"] is True
    assert payload["native_host"] is True
    assert payload["socket"] == str(socket_path)
    assert payload["socket_exists"] is True
    assert payload["hermes_home"] == str(hermes_home)
    assert "diagnostics" in payload
    assert payload["preflight_ok"] is False
    assert "chrome_native_manifest" in payload["blocking_checks"]


def test_diagnostics_catches_manifest_and_socket_regressions(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes-home"
    extension_dir = hermes_home / "chrome-bridge" / "extension"
    native_dir = hermes_home / "chrome-bridge" / "native"
    manifest_dir = tmp_path / "NativeMessagingHosts"
    extension_dir.mkdir(parents=True)
    native_dir.mkdir(parents=True)
    manifest_dir.mkdir()
    (extension_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "Hermes Chrome Bridge",
                "manifest_version": 3,
                "permissions": ["nativeMessaging", "scripting"],
                "background": {"service_worker": "service_worker.js"},
                "web_accessible_resources": [
                    {"resources": ["images/pointer-shape-animated.svg"], "matches": ["<all_urls>"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    (extension_dir / "service_worker.js").write_text("", encoding="utf-8")
    native_host_path = native_dir / "native_host.py"
    native_host_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    native_host_path.chmod(0o755)
    (manifest_dir / "com.hermes.chrome_bridge.json").write_text(
        json.dumps(
            {
                "name": "com.hermes.chrome_bridge",
                "path": str(tmp_path / "wrong-native-host.py"),
                "type": "stdio",
                "allowed_origins": ["chrome-extension://abcdefghijklmnopabcdefghijklmnop/"],
            }
        ),
        encoding="utf-8",
    )
    socket_path = tmp_path / "chrome.sock"
    socket_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_CHROME_BRIDGE_SOCKET", str(socket_path))
    monkeypatch.setattr(tools, "_native_manifest_dir", lambda: manifest_dir)

    payload = tools._diagnostics()

    assert payload["checks"]["runtime_extension_manifest"] is True
    assert payload["extension_manifest"]["has_cursor_asset"] is True
    assert payload["native_manifest"]["allowed_extension_ids"] == ["abcdefghijklmnopabcdefghijklmnop"]
    assert payload["socket"]["stale_reason"] == "Path exists but is not a Unix socket"
    assert "native_manifest_host_matches_runtime" in payload["blocking_checks"]
    assert "socket_path_is_clean_or_live" in payload["blocking_checks"]


def test_build_extension_request_preserves_actions():
    request = {
        "action": "run",
        "actions": [{"type": "goto", "url": "https://example.com"}, {"type": "text"}],
        "sessionName": "Hermes Test",
        "taskId": "task-3",
        "useSelectedTab": True,
        "maxTextChars": 1234,
    }

    payload = tools._build_extension_request(request, timeout_seconds=17)

    assert payload == {
        "type": "run",
        "actions": request["actions"],
        "timeoutSeconds": 17,
        "sessionName": "Hermes Test",
        "taskId": "task-3",
        "useSelectedTab": True,
        "maxTextChars": 1234,
    }


def test_build_extension_status_request():
    payload = tools._build_extension_request({"action": "status"}, timeout_seconds=9)

    assert payload == {"type": "status", "timeoutSeconds": 9}


def test_build_request_accepts_diagnostics():
    request = tools._build_bridge_request({"action": "diagnose"}, task_id="task-d")

    assert request["action"] == "diagnose"
    assert request["taskId"] == "task-d"


def test_health_check_combines_diagnostics_and_status(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_diagnostics",
        lambda: {"preflight_ok": True, "blocking_checks": [], "success": True},
    )
    monkeypatch.setattr(
        tools,
        "_run_extension_bridge",
        lambda request, timeout_seconds: {
            "success": True,
            "content_script": {"injected": True},
            "active_tab": {"url": "https://example.com"},
        },
    )

    payload = tools._health_check(timeout_seconds=7)

    assert payload["ready"] is True
    assert payload["selected_tab_ready"] is True
    assert payload["blocking_checks"] == []
    assert payload["bridge_status"]["active_tab"]["url"] == "https://example.com"


def test_health_check_skips_bridge_when_diagnostics_block(monkeypatch):
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        return {"success": False}

    monkeypatch.setattr(
        tools,
        "_diagnostics",
        lambda: {"preflight_ok": False, "blocking_checks": ["socket_path_is_clean_or_live"], "success": True},
    )
    monkeypatch.setattr(tools, "_run_extension_bridge", fail_if_called)

    payload = tools._health_check(timeout_seconds=7)

    assert payload["ready"] is False
    assert payload["selected_tab_ready"] is False
    assert payload["blocking_checks"] == ["socket_path_is_clean_or_live"]
    assert called is False


def test_health_ready_when_bridge_works_but_selected_tab_probe_fails(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_diagnostics",
        lambda: {"preflight_ok": True, "blocking_checks": [], "success": True},
    )
    monkeypatch.setattr(
        tools,
        "_run_extension_bridge",
        lambda request, timeout_seconds: {
            "success": True,
            "content_script": {"injected": False, "blocked": True, "reason": "Content script did not respond"},
            "active_tab": {"url": "https://example.com"},
        },
    )

    payload = tools._health_check(timeout_seconds=7)

    assert payload["ready"] is True
    assert payload["selected_tab_ready"] is False


def test_run_extension_bridge_round_trips_over_socket(monkeypatch):
    socket_path = Path("/tmp") / f"hermes-chrome-test-{os.getpid()}.sock"
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass
    seen = []

    def server():
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(socket_path))
        srv.listen(1)
        conn, _ = srv.accept()
        with conn:
            data = conn.recv(65536)
            seen.append(json.loads(data.decode("utf-8")))
            conn.sendall(b'{"success": true, "final_url": "https://example.com"}')
        srv.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    for _ in range(50):
        if socket_path.exists():
            break
        time.sleep(0.01)
    monkeypatch.setenv("HERMES_CHROME_BRIDGE_SOCKET", str(socket_path))

    result = tools._run_extension_bridge(
        {"action": "run", "actions": [{"type": "text"}], "sessionName": "Test", "taskId": "t"},
        timeout_seconds=5,
    )
    thread.join(timeout=2)

    assert result == {"success": True, "final_url": "https://example.com"}
    assert seen == [
        {
            "type": "run",
            "actions": [{"type": "text"}],
            "timeoutSeconds": 5,
            "sessionName": "Test",
            "taskId": "t",
            "useSelectedTab": False,
            "maxTextChars": 20000,
        }
    ]
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass


def test_handle_returns_tool_error_for_bridge_failure(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_run_extension_bridge",
        lambda request, timeout_seconds: {"success": False, "error": "no extension"},
    )

    payload = json.loads(tools._handle_hermes_chrome_browser({"action": "status"}))

    assert payload["success"] is False
    assert payload["error"] == "no extension"


def test_native_host_materializes_screenshot_under_hermes_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))

    response = native_host._materialize_response(
        {
            "id": "abc",
            "success": True,
            "results": [{"type": "screenshot", "base64": "iVBORw0KGgo="}],
        }
    )

    result = response["results"][0]
    assert "base64" not in result
    screenshot_path = Path(result["screenshot_path"])
    assert screenshot_path == tmp_path / "hermes-home" / "cache" / "hermes-chrome" / "abc-0.png"
    assert screenshot_path.read_bytes() == b"\x89PNG\r\n\x1a\n"
