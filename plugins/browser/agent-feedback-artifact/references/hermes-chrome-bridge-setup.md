# Hermes Chrome Bridge Setup

Complete setup and teardown for the Hermes Chrome Bridge Chrome extension and cursor overlay.

## Overview

The Hermes Chrome Bridge provides:
- **Headed browser control** — navigate, click, type, take screenshots in the user's signed-in Chrome
- **Floating cursor overlay** — a visible blue glowing dot that shows where the AI agent is interacting
- **Real-time interaction** — the user watches the agent work live in Chrome, not headless

## Architecture

```
Hermes Agent (OWL)
  └─ hermes_chrome_browser tool
       └─ Unix socket ~/.hermes/run/chrome-bridge.sock
            └─ native_host.py
                 ├─ stdin/stdout ↔ Chrome extension service_worker.js
                 └─ chrome.debugger API ↔ Tab CDP
                      └─ content_scripts/cursor-agent.js (injected into every page)
```

Cursor action flow: `hermes_chrome_browser` → socket → `native_host.py` → native messaging → `service_worker.js` → `chrome.tabs.sendMessage` → `cursor-agent.js` → CSS transform update.

## Installation

1. Add `hermes_chrome` to `known_plugin_toolsets` in `~/.hermes/config.yaml`
2. `python3 plugins/browser/hermes_chrome/scripts/install_hermes_chrome_bridge.py --install-runtime`
3. Load unpacked extension from `~/.hermes/chrome-bridge/extension/` in `chrome://extensions`
4. Install NM manifest with extension ID
5. Reload extension; verify socket at `~/.hermes/run/chrome-bridge.sock`

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Access to the specified native messaging host is forbidden" | Reinstall NM manifest with correct full ID, reload extension |
| Cursor overlay not visible | Page must be served via `http://`, not `file://` |
| "Cannot access a chrome:// URL" | SW now filters out chrome:// URLs in `currentTab()` |
| Content script not injected after update | Reload extension + refresh target page |
| Popup shows "Disconnected" | Native host is single-connection; popup probes via scripting API instead |

## Key Rules

- **Never use `file://` URLs** — content scripts and CORS fetch don't work. Always serve via `http://localhost:<port>/`.
- **Native messaging is single-connection** — SW holds it, popup cannot `connectNative()`.
- **Filter chrome:// URLs** from `chrome.tabs.query` results in `currentTab()`.
- **Reload extension** after any manifest or SW change.
- **Chrome MV3 CSP blocks inline `<script>` in popup** — all popup JS must be in external `popup.js`.