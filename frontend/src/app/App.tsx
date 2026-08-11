import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { TooltipProvider } from "@/components/ui";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { router } from "@/routes";
import { useAuthStore } from "@/store/authStore";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/** Exchanges a persisted refresh token (if any) for a fresh session exactly once per app
 * mount -- guarded on `status === "idle"` so React 19 `StrictMode`'s double-invoke in
 * development doesn't fire it twice. `RequireAuth` shows a loading state for as long as this
 * takes, then redirects to `/login` or renders the app depending on the outcome.
 */
function useSessionRestore(): void {
  useEffect(() => {
    if (useAuthStore.getState().status === "idle") {
      void useAuthStore.getState().restoreSession();
    }
  }, []);
}

export function App() {
  useSessionRestore();

  return (
    <ErrorBoundary section="the application">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
