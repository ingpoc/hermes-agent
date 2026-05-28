#!/usr/bin/env python3
"""Install the Hermes Chrome Bridge native messaging manifest."""

from __future__ import annotations

import argparse
import shutil
import json
import platform
from pathlib import Path


HOST_NAME = "com.hermes.chrome_bridge"


def hermes_home() -> Path:
    import os

    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()


def runtime_root() -> Path:
    return hermes_home() / "chrome-bridge"


def runtime_info(*, ensure_native: bool = False) -> dict:
    root = runtime_root()
    extension_dir = root / "extension"
    source_native_host = Path(__file__).resolve().parents[1] / "native" / "native_host.py"
    native_host = root / "native" / "native_host.py"
    if ensure_native:
        native_host.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_native_host, native_host)
        native_host.chmod(native_host.stat().st_mode | 0o111)
    return {
        "runtime_root": str(root),
        "extension_dir": str(extension_dir),
        "native_host": str(native_host),
    }


def native_manifest_dir() -> Path:
    system = platform.system().lower()
    home = Path.home()
    if system == "darwin":
        return home / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"
    if system == "linux":
        return home / ".config" / "google-chrome" / "NativeMessagingHosts"
    raise SystemExit(f"Unsupported platform for installer: {platform.system()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension-id", help="Chrome extension id after loading the unpacked extension.")
    parser.add_argument("--install-runtime", action="store_true", help="Print the existing HERMES_HOME runtime paths.")
    parser.add_argument(
        "--native-host",
        default=None,
        help="Absolute path to native_host.py.",
    )
    parser.add_argument(
        "--manifest-dir",
        help="Override Chrome NativeMessagingHosts directory. Intended for tests and custom profiles.",
    )
    args = parser.parse_args()

    info = runtime_info(ensure_native=args.install_runtime) if args.install_runtime else None
    if not args.extension_id:
        if info:
            print(json.dumps({"success": True, **info}))
            return 0
        raise SystemExit("--extension-id is required unless --install-runtime is used by itself")

    native_host = Path(
        args.native_host or (info or {}).get("native_host") or Path(__file__).resolve().parents[1] / "native" / "native_host.py"
    ).expanduser().resolve()
    if not native_host.exists():
        raise SystemExit(f"Native host not found: {native_host}")

    manifest = {
        "name": HOST_NAME,
        "description": "Hermes Chrome Bridge native messaging host",
        "path": str(native_host),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{args.extension_id}/"],
    }
    manifest_dir = Path(args.manifest_dir).expanduser() if args.manifest_dir else native_manifest_dir()
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{HOST_NAME}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "success": True,
        **(info or {}),
        "manifest_path": str(manifest_path),
        "native_host": str(native_host),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
