# Codex Chrome Extension Architecture — Key Learnings

## Extension Injection Pattern

Codex does NOT use manifest `content_scripts`. It uses **programmatic-only injection** via `chrome.scripting.executeScript()`. The Hermes Chrome Bridge now matches this pattern.

Key files in the runtime extension (`~/.hermes/chrome-bridge/extension/`):

| File | Role |
|---|---|
| `manifest.json` | MV3 manifest — NO `content_scripts` key |
| `service_worker.js` | Auto-injects content script via `chrome.tabs.onUpdated` + `scripting.executeScript`; tracks `injectedTabs` Set |
| `content-scripts/cursor-agent.js` | Floating cursor overlay; sets both `document.documentElement.dataset.hermesAgentCursorInjected` (DOM, cross-world visible) and `window.__hermesAgentCursorInjected` (isolated world guard) |
| `popup.js` | Dual-strategy probing: (1) queries SW `injectedTabs` via `chrome.runtime.sendMessage({type:'hermes-cursor-status'})`, (2) falls back to DOM attribute probe |
| `images/pointer-shape-animated.svg` | Cursor pointer SVG — loaded via `chrome.runtime.getURL()` |

## Popup Content Script Detection — Timing Issue

**Symptom:** Popup shows "Content Script: Not yet — refresh the page" even though extension is loaded.

**Root cause:** The service worker's `injectedTabs` Set is populated by two triggers:
1. `chrome.tabs.onUpdated(status='complete')` → auto-injects on page load
2. Content script sends `'hermes-cursor-ready'` message on init

If the page was already loaded before the extension was reloaded, `tabs.onUpdated` never fires for that tab. The `injectedTabs` Set is empty until the next navigation.

**Fix:** After any extension reload, the user must navigate (click a link, press Enter on address bar) or refresh the target page. This is expected Chrome extension lifecycle behavior — not a bug.

**Reliable popup probe sequence:**
1. SW checks `injectedTabs.has(tabId)` — if yes, return `{injected: true}`
2. If not, SW calls `chrome.scripting.executeScript()` to re-inject
3. SW probes via `chrome.tabs.sendMessage({action: 'getStatus'})` — if response, mark as injected
4. Popup shows "Injected ✓" only after positive response

## Cursor Visibility

The cursor starts at `(-100, -100)` with `opacity: 0` (class `hermes-visible` NOT applied). Calling `cursor_move` via:
- `hermes_chrome_browser` tool: `{"type": "cursor_move", "x": 500, "y": 350}`
- Or SW internal: `sendToContentScript(tabId, "moveTo", [x, y])`

...triggers `moveTo()` in the content script which adds `hermes-visible` class, making the cursor appear.

The animation loop uses `lerp = 0.25` for smooth movement. Status returns `phase: "moving"` → `"arrived"` → `"idle"`.

## Critical: `tabs.onUpdated` and Service Worker Lifecycle

**SW restart gotcha:** Chrome kills the service worker after ~30s of inactivity. When the SW restarts, all in-memory state (including `injectedTabs`) is lost, but content scripts in already-loaded pages keep running.

**Current mitigation:** `tabs.onUpdated` fires on each page load/reload and re-injects. The popup's `ensureContentScript()` fallback via `chrome.tabs.sendMessage('getStatus')` catches the case where SW state was lost but content script is still alive in the page.

## Hermes Chrome Bridge vs Codex Extension — Feature Comparison

| Feature | Codex | Hermes Bridge |
|---|---|---|
| Manifest content_scripts | ❌ None | ❌ None |
| Programmatic injection | ✅ `executeScript()` | ✅ `executeScript()` via `tabs.onUpdated` |
| Cursor overlay | ✅ Custom pointer SVG | ✅ `pointer-shape-animated.svg` |
| SW tab tracking | `tabSessions` Map | `injectedTabs` Set |
| Popup→SW messaging | `chrome.runtime.sendMessage(GET_AGENT_CURSOR_TYPE)` | `chrome.runtime.sendMessage({type:'hermes-cursor-status'})` |
| Content script ready ping | ✅ | ✅ `'hermes-cursor-ready'` |
| DOM injection flag | ✅ `dataset` attribute | ✅ `dataset.hermesAgentCursorInjected` |
| Native messaging | Custom host | `native_host.py` via stdio + Unix socket |
| Socket path | N/A | `~/.hermes/run/chrome-bridge.sock` |

## Full Verification Flow

After any extension code change:
1. Reload extension in `chrome://extensions`
2. Navigate target page (full page load, not just hash change)
3. Click extension icon → verify "Connected — OWL is ready" + "Content Script: Injected ✓"
4. `hermes_chrome_browser` `cursor_move` → cursor visible on page
5. `cursor_status` → `{visible: true, x: <moved_x>, y: <moved_y>, phase: 'idle'}`
