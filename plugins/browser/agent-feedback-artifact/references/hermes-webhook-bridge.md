# Hermes Webhook Event Bridge

When the feedback server runs with `AGENT_FEEDBACK_WEBHOOK_URL`, every new
marker comment triggers an immediate POST to that URL containing the full work
item summary. This replaces polling with push.

## Architecture

```
Operator comments in browser
  → Widget POSTs /api/feedback
    → Server creates queue entry
      → Server POSTs to AGENT_FEEDBACK_WEBHOOK_URL (fire-and-forget)
        → Hermes webhook triggers agent run with full context
          → Agent dispatch/claim, process, mark done
            → Widget polls /api/feedback/status and shows reply
```

No cron. No manual polling. ~1s latency from comment to agent pickup.

## Setup (Preflight)

After starting the feedback server, create a Hermes webhook subscription that
routes to this skill:

```bash
# 1. Ensure the Hermes webhook platform is enabled
hermes gateway setup  # or add platforms.webhook to config.yaml

# 2. Create a webhook subscription for this artifact
hermes webhook subscribe artifact-feedback-<slug> \
  --prompt "New artifact feedback comment on {artifactPath}. Work ID: {items[0].id}, Route: {items[0].route}, Marker: {items[0].visibleText}, Message: {items[0].latestUserMessage}. Use the agent-feedback-artifact skill to process this marker. Run dispatch to claim, then process per route." \
  --skills "agent-feedback-artifact" \
  --deliver origin \
  --events "artifact_feedback_new"
```

The webhook URL returned by `hermes webhook subscribe` becomes the value of
`AGENT_FEEDBACK_WEBHOOK_URL`. Pass it when starting the server:

```bash
AGENT_FEEDBACK_WEBHOOK_URL="http://localhost:8644/hooks/artifact-feedback-<slug>" \
AGENT_FEEDBACK_WEBHOOK_SECRET="$(hermes webhook list --json | jq -r '.[] | select(.name=="artifact-feedback-<slug>") | .secret')" \
  node scripts/artifact-feedback-server.mjs <serve-root> <port>
```

If `AGENT_FEEDBACK_WEBHOOK_SECRET` is set, the server signs each POST with
HMAC-SHA256 in the `x-agent-feedback-signature` header. Hermes validates this
signature on receipt.

## Teardown (Closeout)

Before stopping the server, remove the webhook subscription:

```bash
hermes webhook remove artifact-feedback-<slug>
```

Then stop the server and run closeout:

```bash
node scripts/agent-feedback-closeout.mjs <artifact.html> --port <port>
```

## Fallback: No Webhook

If the Hermes webhook platform is not enabled, or `AGENT_FEEDBACK_WEBHOOK_URL`
is not set, the server operates normally — queue items are created but the agent
must poll manually via `/api/agent/next` or `agent-feedback-next.mjs`. This is
acceptable for development but not for production operator use.

## Webhook Payload Shape

The server POSTs this JSON to `AGENT_FEEDBACK_WEBHOOK_URL`:

```json
{
  "event": "artifact_feedback_new",
  "count": 1,
  "items": [
    {
      "id": "afw-...",
      "markerId": "af-...",
      "status": "queued",
      "artifactPath": "/page.html",
      "artifactTitle": "Page Title",
      "selector": "td:nth-child(2)",
      "visibleText": "Salary (Section 17)",
      "latestUserMessage": "Is this figure correct?",
      "route": "deep_marker_worker",
      "contextTier": "T2",
      "workerLifecycle": "fresh_once"
    }
  ],
  "artifact": "/page.html",
  "timestamp": "2026-05-27T12:00:00.000Z"
}
```

Note: `route`, `contextTier`, and `workerLifecycle` are only present when the
server has routing enabled. The Hermes webhook prompt template can use
`{items[0].route}` etc. to dispatch appropriately.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `AGENT_FEEDBACK_WEBHOOK_URL` | No | URL to POST new feedback events to |
| `AGENT_FEEDBACK_WEBHOOK_SECRET` | No | HMAC-SHA256 signing key |
| `AGENT_FEEDBACK_WEBHOOK_TIMEOUT_MS` | No |Request timeout (default: 2500ms) |
| `PORT` | No | Server port (default: 4177) |