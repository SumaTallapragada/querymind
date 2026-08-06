# QueryMind Frontend

Phase 18 of Text-to-SQLAnalyticsEngine: a React + TypeScript UI over the QueryMind FastAPI
backend (Phases 1–17). It is a pure client of the existing REST and streaming APIs -- no
business logic (SQL generation, validation, repair, execution, or result formatting) is
duplicated here. Every number, status, and message shown on screen was computed by the backend.

## Stack

- **React 19 + TypeScript**, built with **Vite**
- **TailwindCSS 4** + **shadcn/ui** (Radix primitives) for styling and components
- **TanStack Query** for server state (REST requests: health, diagnostics, metrics, settings,
  the direct `POST /query` family)
- **Zustand** for client-only state (`queryStore` for a question session -- direct or
  streaming -- `uiStore` for theme/sidebar/transport preference)
- **React Hook Form + Zod** for the question form
- **Recharts** for the Metrics page's charts
- **Vitest + Testing Library + MSW** for tests

No Redux. No client-side reimplementation of anything the backend already does.

## Getting started

```bash
npm install
npm run dev      # http://localhost:5173, proxying /api and /ws to http://localhost:8000
```

The backend (`uvicorn querymind.api.app:app`) must be running separately on port 8000 -- see
the repository root README for how to start it. `vite.config.ts` proxies `/api/*` and `/ws/*`
to `http://localhost:8000` in development, so the app talks to `/api/v1/...` as if same-origin.

### Environment variables

Not required for local development (the Vite proxy covers it). For a non-same-origin deployment,
copy `.env.example` to `.env.local` and set:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | Base URL for every REST call (`services/api.ts`) |
| `VITE_WS_BASE_URL` | derived from `window.location` | Base URL for `/ws/query` (`services/streaming.ts`) |

## Scripts

| Script | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check (`tsc -b`) then production-build |
| `npm run lint` | oxlint |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run test` | Run the Vitest suite once |
| `npm run test:watch` | Run Vitest in watch mode |
| `npm run test:coverage` | Run the suite with a v8 coverage report |
| `npm run preview` | Preview a production build locally |

## Architecture

```
src/
  app/            App.tsx: provider tree (ErrorBoundary > QueryClientProvider > TooltipProvider > RouterProvider)
  routes/         React Router route table
  pages/          One folder per route: Dashboard, Diagnostics, Health, Metrics, Settings
  components/     Presentational + feature components (see below), plus components/ui (shadcn/ui primitives)
  hooks/          TanStack Query hooks (server state) and useStreaming/useClipboard (client behavior)
  services/       api.ts (REST) and streaming.ts (SSE/WebSocket) -- the only files that call fetch/WebSocket
  store/          Zustand stores: queryStore (question session), uiStore (theme/sidebar/transport)
  models/         TypeScript types mirroring every backend Pydantic model 1:1, snake_case field names kept as-is
  utils/          Pure functions: stream event -> response derivation, CSV export, error messages, ...
  tests/          Vitest suite: components/, hooks/, pages/, integration/, mocks/ (MSW), setup.ts
```

### Data flow

1. **Direct mode** (`POST /query`): `QueryInput` calls `useAskQuestion` (`hooks/useQuery.ts`), a
   TanStack `useMutation` wrapping `services/api.ts#askQuestion`. `queryStore` tracks the
   session's lifecycle (`idle -> running -> settled | transport_error`) so every panel renders
   from one source of truth regardless of how the response arrived.
2. **Streaming mode** (`POST /query/stream` over SSE, or `/ws/query` over WebSocket):
   `useStreaming` (`hooks/useStreaming.ts`) opens a connection via `services/streaming.ts` and
   forwards each `PipelineEvent` into `queryStore.appendEvent`. `utils/streamingDerivation.ts`
   reshapes the accumulated events into the same `QueryMindResponse` shape a direct call
   produces, once a `pipeline_completed`/`pipeline_failed` event arrives -- so `PipelineTimeline`,
   `SQLViewer`, `ResultTable`, etc. render identically for both modes.
3. **Everything else** (Health, Diagnostics, Metrics, Settings pages) is a plain TanStack `useQuery`
   against its REST endpoint -- no client state beyond React Query's own cache.

### Why two stores, not one

`queryStore` is genuinely a stream of events over time (not one cacheable request/response),
so it lives outside TanStack Query. `uiStore` is UI-only preference state (theme, sidebar,
which streaming transport to demonstrate) that should survive a page reload, so it uses
Zustand's `persist` middleware against `localStorage`. Anything that *is* cacheable server data
(health, diagnostics, metrics, settings, a direct query's response) goes through TanStack Query
instead of either store.

## Testing

`src/tests/` mirrors the coverage a Phase 18 frontend needs:

- `utils/`, `store/` -- pure logic, no rendering
- `hooks/` -- TanStack Query hooks against MSW-mocked endpoints; `useStreaming` against a mocked
  `services/streaming.ts`
- `components/` -- one file per component with meaningful behavior (data-driven rendering, user
  interaction, empty/error states)
- `pages/` -- loading/data/error states for each route, against MSW
- `integration/` -- a full direct-mode question flow and a full streaming-mode question flow,
  end to end through `QueryInput` -> the hooks -> `queryStore` -> `DashboardPage`'s panels

`tests/mocks/` holds one MSW handler per REST endpoint (`handlers.ts`) and one fixture per
backend DTO (`fixtures.ts`), reused across every test rather than redefined per file.

Run `npm run test` before every commit that touches `src/`; `npm run test:coverage` for a
coverage report under `coverage/`.