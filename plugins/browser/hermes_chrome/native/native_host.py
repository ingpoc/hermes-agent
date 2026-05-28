#!/usr/bin/env python3
"""Native messaging host for the Hermes Chrome Bridge extension."""

from __future__ import annotations

import json
import os
import queue
import socket
import struct
import sys
import threading
import uuid
import base64
from pathlib import Path
from typing import Any


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()


SOCKET_PATH = hermes_home() / "run" / "chrome-bridge.sock"
pending: dict[str, queue.Queue[dict[str, Any]]] = {}
pending_lock = threading.Lock()
out_lock = threading.Lock()


def read_native_message() -> dict[str, Any] | None:
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len:
        return None
    length = struct.unpack("<I", raw_len)[0]
    data = sys.stdin.buffer.read(length)
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def write_native_message(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    with out_lock:
        sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()


def socket_server() -> None:
    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(10)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


def handle_client(conn: socket.socket) -> None:
    with conn:
        request = json.loads(conn.recv(10_000_000).decode("utf-8"))
        request_id = str(uuid.uuid4())
        response_q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with pending_lock:
            pending[request_id] = response_q
        write_native_message({"id": request_id, **request})
        try:
            response = response_q.get(timeout=float(request.get("timeoutSeconds", 45)))
            response = _materialize_response(response)
        except queue.Empty:
            response = {"id": request_id, "success": False, "error": "Hermes Chrome extension timed out"}
        finally:
            with pending_lock:
                pending.pop(request_id, None)
        conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))


def _materialize_response(response: dict[str, Any]) -> dict[str, Any]:
    """Persist large binary artifacts from extension responses under HERMES_HOME."""
    results = response.get("results")
    if not isinstance(results, list):
        return response
    screenshot_dir = hermes_home() / "cache" / "hermes-chrome"
    for index, item in enumerate(results):
        if not isinstance(item, dict) or item.get("type") != "screenshot":
            continue
        data = item.pop("base64", None)
        if not isinstance(data, str):
            continue
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = screenshot_dir / f"{response.get('id') or 'capture'}-{index}.png"
        path.write_bytes(base64.b64decode(data))
        item["screenshot_path"] = str(path)
    return response


def main() -> int:
    threading.Thread(target=socket_server, daemon=True).start()
    while True:
        message = read_native_message()
        if message is None:
            return 0
        request_id = str(message.get("id") or "")
        with pending_lock:
            response_q = pending.get(request_id)
        if response_q is not None:
            response_q.put(message)


if __name__ == "__main__":
    raise SystemExit(main())
