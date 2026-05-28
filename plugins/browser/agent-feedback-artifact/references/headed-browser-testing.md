# Headed Browser Testing for Agent Feedback Widget

Patterns for driving a visible Chromium browser to test the feedback widget
interactively — the user can watch markers appear, agent replies sync, and the
widget respond in real-time.

## Why headed testing?

The `browser_*` tools run headless Playwright — invisible to the user. When
testing UI features like the feedback widget, the user often wants to **watch**
the test happen. This requires Playwright `headless=False`.

## Approach 1: Python Playwright script (recommended for test suites)

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:4177/page.html")
    page.wait_for_load_state("networkidle")

    # Interact via page.evaluate()
    page.evaluate("document.querySelector('.af-launcher').click()")

    page.wait_for_timeout(30000)  # keep open for visual inspection
    browser.close()
```

Key patterns:
- **Click launcher**: `page.evaluate("document.querySelector('.af-launcher').click()")`
- **Arm overlay**: `page.evaluate("...querySelector('.af-button[data-af-toggle]').click()")`
- **Place marker**: dispatch `MouseEvent` on `.af-layer` at computed coordinates
- **Type comment**: always pass dynamic text as a `page.evaluate` **function argument**,
  never as f-string interpolation (quotes/backslashes break)
- **Verify queue**: `urllib.request.urlopen("http://localhost:PORT/api/agent/next")`
- **Agent reply**: `agent-feedback-mark.mjs <work-id> done "Reply text" --summary "Summary"`
- **Verify sync**: poll `localStorage` for `agent` role messages (widget polls every 5s)

Prerequisites:
```bash
pip3 install playwright
playwright install chromium
```

## Approach 2: Pipe-file bridge for real-time interactive driving

When driving the browser **step by step from the terminal** (each command sent
individually, result read back), use the pipe-file pattern. This avoids
Playwright's thread-safety limitation (`evaluate()` must run on the main thread).

```python
#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import json, os, time

COMMAND_FILE = '/tmp/browser-cmd.json'
RESULT_FILE = '/tmp/browser-result.json'
READY_FLAG = '/tmp/browser-ready.flag'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto('http://localhost:4178/page.html')
    page.wait_for_load_state('networkidle')

    with open(READY_FLAG, 'w') as f:
        f.write('ready')

    while True:
        if os.path.exists(COMMAND_FILE):
            try:
                with open(COMMAND_FILE, 'r') as f:
                    cmd = f.read().strip()
                os.remove(COMMAND_FILE)

                if cmd == '__EXIT__':
                    with open(RESULT_FILE, 'w') as f:
                        f.write(json.dumps({'ok': True, 'result': 'exiting'}))
                    break

                result = page.evaluate(cmd)
                with open(RESULT_FILE, 'w') as f:
                    f.write(json.dumps({'ok': True, 'result': result}))
            except Exception as e:
                try: os.remove(COMMAND_FILE)
                except: pass
                with open(RESULT_FILE, 'w') as f:
                    f.write(json.dumps({'ok': False, 'error': str(e)}))

        page.wait_for_timeout(200)

    browser.close()
```

Send commands from the terminal:
```bash
rm -f /tmp/browser-result.json
echo "document.querySelector('.af-launcher').click(); 'clicked'" > /tmp/browser-cmd.json
sleep 0.5
cat /tmp/browser-result.json
```

HTTP bridges fail because Playwright sync API throws
`Cannot switch to a different greenlet` when calling `page.evaluate()` from a
different thread. The pipe-file poll pattern keeps everything on the main
thread.

## Why not computer_use for widget testing?

The `.af-layer` overlay uses `pointer-events: auto` when armed and
`elementsFromPoint` hit-testing that temporarily disables overlay nodes.
`computer_use` coordinate clicks bypass this logic because they don't fire real
pointer events through the DOM event system. Use Playwright's `page.evaluate()`
with `dispatchEvent(new MouseEvent(...))` instead.

## Why not osascript for Comet browser control?

Comet supports `do JavaScript` via Apple Events (when "Allow JavaScript from
Apple Events" is enabled in Developer menu), but AppleScript's parser chokes on
JavaScript reserved words like `class` (in `classList`, `className`) even
inside double-quoted strings. Workarounds (base64 encoding, JXA) are fragile.
Use Playwright for reliable widget testing.

## Playwright evaluate() argument passing

Always pass dynamic values (comments, selectors) as **function arguments**,
not f-string interpolation:

```python
# ✅ Correct — pass as argument, no escaping issues
page.evaluate("""(comment) => {
    const inp = document.querySelector('[data-af-popover-input]');
    inp.value = comment;
    inp.dispatchEvent(new Event('input', {bubbles: true}));
}""", my_comment_text)

# ❌ Wrong — f-string interpolation breaks on quotes/backslashes
page.evaluate(f"""() => {{
    inp.value = '{comment_text.replace("'", "\\'")}';
}}""")  # SyntaxError: f-string cannot include backslash in expression
```

Playwright locator syntax (`>> text=`, `:has-text()`) only works with
`page.locator()`, not inside `document.querySelector()`. Use valid CSS selectors
in JS evaluate calls.

## Why not cron for event processing?

Cron polling (every 1m) is the wrong architecture for comment-triggered agent
processing. It introduces 30-60s latency, wastes cycles polling empty queues,
and has no context about which artifact/marker triggered the event.

The correct architecture is **webhook event bridge**: the feedback server POSTs
to `AGENT_FEEDBACK_WEBHOOK_URL` when new items are queued, which triggers the
agent immediately with full context (work ID, route, marker message, selector).
This gives ~1s latency, zero waste, and rich context without the agent needing
to poll and discover what changed.

The server supports `AGENT_FEEDBACK_WEBHOOK_URL` and `AGENT_FEEDBACK_WEBHOOK_SECRET`
environment variables. When set, `POST /api/feedback` fires a fire-and-forget
webhook notification to that URL with the work item details.

## Clearing stale queue items before testing

Always clear stale items before running E2E tests:

```python
import json, urllib.request
while True:
    resp = urllib.request.urlopen("http://localhost:PORT/api/agent/next", timeout=3)
    data = json.loads(resp.read())
    if not data.get("item"):
        break
    subprocess.run(["node", MARK_SCRIPT, data["item"]["id"], "canceled", "Stale test item"],
                   capture_output=True, cwd=ARTIFACT_DIR)
```