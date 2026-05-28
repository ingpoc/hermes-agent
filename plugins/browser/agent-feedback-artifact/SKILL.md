---
name: agent-feedback-artifact
description: "Use when the user wants in-page annotation widget on HTML artifacts,
  marker-local chat, or comment-triggered agent work. Add, serve, queue, and
  process marker feedback. Triggers: annotation, feedback, marker, artifact."
---

# Agent Feedback Artifact

> **Self-validate after edits.** Run `./scripts/validate.sh` from the skill directory after any change.

Injects a managed annotation widget into an HTML artifact, serves it through a local feedback server, and queues marker-scoped user comments as agent work items.

## Operating Sequence

```
preflight → add widget → serve page → annotate/process → closeout
```

1. **Preflight:** `node scripts/agent-feedback-preflight.mjs <artifact.html> --port <port>`
2. **Add widget:** `node scripts/add-agent-feedback.mjs <artifact.html>` (injects `AGENT_FEEDBACK_WIDGET_START..END` block)
3. **Serve:** `node scripts/artifact-feedback-server.mjs <serve-root> <port>`
4. **Annotate (browser):** Open `http://localhost:<port>/<file>` (use the explicit filename like `index.html`, NOT just `/` — processing scripts resolve artifact path from `location.pathname` and bare `/` causes `EISDIR` errors) → click `.af-launcher` (top-right toggle) → click `[data-af-toggle]` (Annotate button, arms overlay) → click target element (layer intercepts with `elementAtPoint`) → type in `[data-af-popover-input]` → click `.af-popover-send`. Selectors: launcher=`.af-launcher`, annotate=`[data-af-toggle]`, input=`[data-af-popover-input]` (NOT `.af-popover-input`). Marker created with `pendingComment`, committed on send.

   **CDP contract:** click_selector, fill_selector, evaluate need CDP (`chrome.debugger`). If the bridge returns `"Another debugger is already attached"`, Chrome DevTools is open on the tab. Follow the bridge skill's CDP recovery: `close_tab` then `goto` to create a fresh tab without DevTools.
5. **Process queue:** `node scripts/agent-feedback-next.mjs --root <serve-root>` → `agent-feedback-details.mjs <id> --root <serve-root>` → Fix → `agent-feedback-mark.mjs <id> done "reply" --root <serve-root>`
6. **Closeout:** `node scripts/agent-feedback-closeout.mjs <artifact.html> --port <port>`

**--root is required** for queue scripts. Points scripts at the server's `data/` directory. Without it, scripts read `process.cwd()/data/` and fail.

## Script Inventory

| Script | Purpose |
|---|---|
| `add-agent-feedback.mjs` | Inject widget before `</body>` |
| `remove-agent-feedback.mjs` | Remove managed block (roundtrip-safe) |
| `artifact-feedback-server.mjs` | Static serving + `/api/feedback/*` + queue |
| `agent-feedback-preflight.mjs` | Readiness checks |
| `agent-feedback-closeout.mjs` | Read-only state report |
| `agent-feedback-next.mjs` | Next queued item |
| `agent-feedback-details.mjs <id>` | Full marker payload |
| `agent-feedback-mark.mjs <id> <status> [reply]` | Update status + agent reply |
| `agent-feedback-routing.mjs` | Route selection (see refs) |
| `agent-feedback-dispatch.mjs` | Direct/worker decision |

## Routing Rules

`classifyWorkItem` decides route based on intent keywords:

| If intent matches | Route to |
|---|---|
| `styleIntent` words (bigger, font, color, spacing, padding, margin, ui, style, layout, button, icon, copy, text, etc.) | `no_worker_main_agent_direct` |
| `dataIntent` words (total, gross, tax, income, calculate, amount, number, incorrect, wrong, `₹`, `rs.`) | `deep_marker_worker` |
| Both match | Prefer style if style word count ≥ data word count |

selector is evidence, not intent — do not classify by `data-*` attributes.

## Closeout

Always run `closeout.mjs`. Report: widget state, server state, webhook config, queue counts, browser evidence, cleanup commands.

## Load References On Need

| When | Load |
|---|---|
| Webhook-triggered processing setup | `references/hermes-webhook-bridge.md` |
| CORS issues with widget fetch | `references/cors-setup.md` |
| River acceptance test checklist | `references/browser-acceptance.md` *(see below)* |
| Hermes Chrome Bridge for headed testing | `hermes-chrome-bridge` skill |
| Widget HTML/CSS/JS internals | `references/overlay.html` |

## Why This Exists

Artifact feedback is lossy via chat (operator describes, agent guesses). This skill makes the artifact the feedback surface, captures marker-scoped intent at source, and gives agents a small default packet with deeper context available on demand.
