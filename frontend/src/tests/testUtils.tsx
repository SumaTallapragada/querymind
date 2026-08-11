/** Shared render helpers -- not a test file itself (no `*.test.tsx` suffix, so vitest never
 * collects it directly). Every hook/component test that touches TanStack Query or routing goes
 * through here instead of hand-rolling its own provider tree.
 */

import type { ReactElement, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, type RenderHookOptions, type RenderOptions } from "@testing-library/react";
import {
  createMemoryRouter,
  MemoryRouter,
  RouterProvider,
  type InitialEntry,
  type RouteObject,
} from "react-router-dom";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function Providers({ children }: { children: ReactNode }) {
  const client = createTestQueryClient();
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">) {
  return render(ui, { wrapper: Providers, ...options });
}

export function renderHookWithProviders<Result, Props>(
  hook: (props: Props) => Result,
  options?: Omit<RenderHookOptions<Props>, "wrapper">,
) {
  return renderHook(hook, { wrapper: Providers, ...options });
}

/** For tests that need real navigation behavior (redirects, `location.state`) rather than the
 * static `MemoryRouter` `renderWithProviders` sets up -- route guards (`RequireAuth`,
 * `RequireRole`) and `LoginPage`'s "already authenticated" redirect both depend on that.
 */
export function renderWithRouter(routes: RouteObject[], options?: { initialEntries?: InitialEntry[] }) {
  const client = createTestQueryClient();
  const router = createMemoryRouter(routes, { initialEntries: options?.initialEntries ?? ["/"] });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}