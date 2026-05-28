# Browser Acceptance Checklist

**Load when:** You need to verify the feedback widget works end-to-end in a browser.

## Minimum Checks

- selecting without comment creates no marker
- first comment creates one marker
- multiple messages stay in one marker thread
- abandoned composer does not leave an empty marker
- UI tab shows selected element context (color, bg, font, size, weight)
- queued message delete removes the message and removes the marker when empty
- processed message shows a done indicator and marker-local agent reply
- marker trash deletes/releases that marker thread
- global trash clears all markers
- reload preserves processed marker status and replies

## Comment-Triggered Processing

- submit at least one marker comment from the page
- verify the server emits webhook or creates a queued work item
- verify processing moves `queued → processing → done/blocked/canceled`
- verify the agent reply appears inside that marker's chat
- do not manually poll and fix as a substitute for trigger verification

## Multi-Marker

- submit 3+ marker comments rapidly without waiting for first to finish
- verify 3 distinct marker IDs
- verify each marker receives its own reply
- verify concurrent processing does not merge markers

## Annotation Flow (Hermes Chrome Bridge)

```
navigate → click launcher (button[data-af-launcher]) → click Annotate (button[data-af-toggle])
→ click_selector("h1") (creates marker, opens popover)
→ fill_selector(".af-popover input", "comment")
→ click_selector(".af-popover-send") (saves + submits)
```

Verify: marker appears on page, popover opens, comment appears in queue via `/api/feedback/status`.
