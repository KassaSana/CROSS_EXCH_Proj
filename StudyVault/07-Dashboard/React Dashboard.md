---
module: dashboard-ui
path: 07-Dashboard
keywords: react, typescript, websocket, vite, charts
---

# React Dashboard

#module-dashboard-ui #pattern-react-state #api-websocket

## Purpose

The dashboard is a Vite React application with two pages: a live dashboard and a statistics page. It loads initial REST data, then uses WebSocket messages for live top-of-book and opportunity updates.

## Key Files

| File | Role |
|---|---|
| `dashboard/src/App.tsx` | Router and shared layout |
| `dashboard/src/api/client.ts` | Typed REST client and API models |
| `dashboard/src/hooks/useWebSocket.ts` | Live connection and message state |
| `dashboard/src/pages/Dashboard.tsx` | Live spreads, feed, status cards |
| `dashboard/src/pages/Statistics.tsx` | Polling aggregates and charts |
| `dashboard/src/components/` | Presentational cards, tables, chart, navigation |

## Internal Flow

```text
REST initial load -> page state
WebSocket message -> useWebSocket -> live state
live state -> components -> rendered dashboard
```

The backend sends Decimal-derived values as strings; the client preserves those values in API types and formats them for display.

## Dependencies

Uses React Router, Recharts, Tailwind, and the backend REST/WebSocket surfaces. It does not access SQLite directly.

## Configuration

Vite proxy and production API settings are in `dashboard/vite.config.ts`, `dashboard/vercel.json`, and the client configuration.

## Testing

Run `npm run typecheck`, `npm run lint`, and `npm run build` from `dashboard/`. Inspect live behavior against `/api/adapters`, `/readyz`, and `/ws/live` when debugging.

## Related Notes

- [[API and Observability]]
- [[System Architecture]]
- [[Quick Reference]]
