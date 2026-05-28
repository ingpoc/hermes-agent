# CORS Setup for artifact-feedback-server.mjs

The browser widget uses `fetch()` to POST to `/api/feedback`. Without CORS headers, the browser silently blocks these requests. This is the #1 cause of "widget doesn't submit feedback."

## What's needed

In `artifact-feedback-server.mjs`, inside the request handler BEFORE any route matching:

```js
// CORS headers for all responses
const origin = req.headers.origin || "*";
res.setHeader("access-control-allow-origin", origin);
res.setHeader("access-control-allow-methods", "GET, POST, DELETE, OPTIONS");
res.setHeader("access-control-allow-headers", "content-type, x-agent-feedback-signature");
res.setHeader("access-control-max-age", "86400");
if (req.method === "OPTIONS") {
  res.writeHead(204);
  res.end();
  return;
}
```

## Quick test

```bash
# Should return 204 with CORS headers
curl -i -X OPTIONS http://localhost:4178/api/feedback \
  -H "Origin: http://localhost:4178" \
  -H "Access-Control-Request-Method: POST"

# Should return CORS headers on GET too
curl -i http://localhost:4178/api/agent/next \
  -H "Origin: http://localhost:4178"
```

Look for `access-control-allow-origin` in the response headers.
