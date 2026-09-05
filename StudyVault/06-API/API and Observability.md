---
module: api
path: 06-API
keywords: fastapi, websocket, readiness, metrics, cors
---

# API and Observability

#module-api #api-rest #api-websocket #pattern-pub-sub

## Purpose

`api.py` creates the FastAPI application, exposes persisted reports and runtime health, and broadcasts live messages to connected browser clients. `metrics.py` defines counters, gauges, and latency instruments.

## Public Surface

REST routes include `/healthz`, `/readyz`, `/api/opportunities/recent`, `/api/stats`, `/api/system/overview`, `/api/system/stats`, `/api/system/timeseries`, `/api/system/reset`, `/api/pairs`, `/api/adapters`, and `/metrics`. `/ws/live` is the live stream.

## Readiness

Readiness is stricter than liveness: every configured adapter must be connected and every tracked book must satisfy the manager's shared eligibility decision. Failure returns HTTP 503 with disconnected adapters and ineligible pairs.

## WebSocket Flow

```text
browser -> connect /ws/live -> broadcaster client set
backend -> broadcast({type, payload}) -> every client
disconnect/error -> remove client
```

The client sends text only to keep the connection alive; server messages carry the data.

## Dependencies

Uses adapters, order books, persistence, shared live message types, and metrics. The React dashboard consumes the API through `dashboard/src/api/client.ts` and `useWebSocket.ts`.

## Testing

Run `python -m pytest server/tests/test_api.py -q`. Cover route payloads, readiness status, window conversion, WebSocket client cleanup, and metrics output.

## Related Notes

- [[Persistence]]
- [[React Dashboard]]
- [[Request Flow]]
