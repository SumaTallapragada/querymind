# QueryMind Frontend

Phase 18 of Text-to-SQLAnalyticsEngine: a React + TypeScript UI over the QueryMind FastAPI
backend (Phases 1–17). It is a pure client of the existing REST and streaming APIs -- no
business logic (SQL generation, validation, repair, execution, or result formatting) is
duplicated here. Every number, status, and message shown on screen was computed by the backend.
Phase 22C adds a login page and session/route/role handling on top -- see
[Authentication](#authentication) below.

## Stack

- **React 19 + TypeScript**, built with **Vite**
- **TailwindCSS 4** + **shadcn/ui** (Radix primitives) for styling and components
- **TanStack Query** for server state (REST requests: health, diagnostics, metrics, settings,
  the direct `POST /query` family, and the `POST /auth/login` mutation)
- **Zustand** for client-only state (`queryStore` for a question session -- direct or
  streaming -- `uiStore` for theme/sidebar/transport preference, `authStore` for the session)
- **React Hook Form + Zod** for the question and login forms
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
  app/            App.tsx: provider tree (ErrorBoundary > QueryClientProvider > TooltipProvider > RouterProvider), starts session restoration
  routes/         React Router route table -- public /login, RequireAuth-gated Layout, per-page RequireRole
  pages/          One folder per route: Dashboard, Diagnostics, Health, Metrics, Settings, Login
  components/     Presentational + feature components (see below), plus components/ui (shadcn/ui primitives), components/Auth (RequireAuth/RequireRole)
  hooks/          TanStack Query hooks (server state) and useStreaming/useClipboard/useAuth (client behavior)
  services/       api.ts (REST, incl. auth token attach/refresh) and streaming.ts (SSE/WebSocket) -- the only files that call fetch/WebSocket
  store/          Zustand stores: queryStore (question session), uiStore (theme/sidebar/transport), authStore (session/tokens/user)
  models/         TypeScript types mirroring every backend Pydantic model 1:1, snake_case field names kept as-is
  utils/          Pure functions: stream event -> response derivation, CSV export, error messages, role-rank comparison, ...
  tests/          Vitest suite: components/, hooks/, pages/, store/, services/, integration/, mocks/ (MSW), setup.ts
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

## Authentication

Phase 22C adds a login page and session handling on top of the Phase 22A/22B backend
(`/api/v1/auth/*`, three ranked roles). The architecture follows the rest of this app: no
parallel client, no JWT parsing duplicated per page.

```
React UI (LoginPage, Sidebar, Topbar)
   |
   v
authStore (Zustand, store/authStore.ts) -- status/accessToken/refreshToken/user
   |
   v
services/api.ts -- attaches Authorization: Bearer <access_token>, refreshes on 401
   |
   v
FastAPI /api/v1/auth/* -> AuthenticationService
```

**Token storage.** The backend returns `access_token`/`refresh_token` as JSON (no HttpOnly
cookie exists to lean on), so both live client-side, but not identically: `authStore` keeps the
short-lived (30 min) access token **in memory only** -- never written to disk -- and persists
only the longer-lived (14 day) refresh token to `localStorage` via `zustand/persist`
(`partialize: (state) => ({ refreshToken: state.refreshToken })`). This is a deliberate
narrowing, not a claim of cookie-level security: anything in `localStorage` is still readable by
an XSS payload, which is why nothing here substitutes for the app's own XSS hygiene (no
`dangerouslySetInnerHTML`, escaped rendering throughout). Neither token is ever logged or
rendered in the UI; the Topbar user menu shows only `username`/`role`.

**Session restoration.** `App.tsx` calls `authStore.restoreSession()` once on mount. If a
refresh token was persisted, it's exchanged for a fresh pair via `POST /auth/refresh`, then
`GET /auth/me` fills in the user profile; either call failing clears the session cleanly. While
this is in flight, `RequireAuth` (`components/Auth/RequireAuth.tsx`) shows a loading state
instead of redirecting, so a valid persisted session never flashes the login page.

**Refresh-on-401.** `services/api.ts#request()` attaches the current access token to every call
except `/auth/login`/`/auth/refresh` (which don't have one yet). On a `401` from any other
endpoint, it refreshes once via a single shared in-flight promise -- so N concurrent 401s trigger
exactly one `/auth/refresh` call, not N -- and retries the original request exactly once. A
failed refresh clears `authStore` (logging the user out) and lets the original error propagate;
since the retry happens at most once per request, an invalid session can never loop.

**Route protection.** `routes/index.tsx`: `/login` is public; every other route is nested under
`RequireAuth` (redirects to `/login`, remembering the requested path via `location.state.from`
for `LoginPage` to send the user back to after signing in). Dashboard/Diagnostics/Metrics/Settings
are additionally wrapped in `RequireRole` with the same floor the backend enforces (`ANALYST` for
Dashboard, `ADMIN` for the rest; Health has none beyond being authenticated) -- see the root
README's [Authorization](../README.md#authorization) table. `Sidebar` filters its nav items the
same way. **This is UX only**: the backend re-validates role on every request regardless of what
the frontend shows or hides.

## Testing

`src/tests/` mirrors the coverage a Phase 18 frontend needs:

- `utils/`, `store/` -- pure logic, no rendering (includes `authStore`'s login/logout/
  restoreSession, and `utils/roles.ts`'s rank comparison)
- `hooks/` -- TanStack Query hooks against MSW-mocked endpoints; `useStreaming` against a mocked
  `services/streaming.ts`
- `services/` -- `apiAuth.test.ts` covers `request()`'s Authorization-header attachment and
  refresh-and-retry behavior directly (header presence, single-flight refresh under concurrent
  401s, a rejected refresh clearing the session without looping)
- `components/` -- one file per component with meaningful behavior (data-driven rendering, user
  interaction, empty/error states), including `RequireAuth`/`RequireRole` (redirect/loading/role
  gating) and the role-aware `Sidebar`/`Topbar` user menu
- `pages/` -- loading/data/error states for each route, against MSW; `LoginPage` covers
  validation, backend error display, duplicate-submit prevention, and post-login redirect
- `integration/` -- a full direct-mode question flow and a full streaming-mode question flow,
  end to end through `QueryInput` -> the hooks -> `queryStore` -> `DashboardPage`'s panels

`tests/mocks/` holds one MSW handler per REST endpoint (`handlers.ts`) and one fixture per
backend DTO (`fixtures.ts`), reused across every test rather than redefined per file.

Run `npm run test` before every commit that touches `src/`; `npm run test:coverage` for a
coverage report under `coverage/`.