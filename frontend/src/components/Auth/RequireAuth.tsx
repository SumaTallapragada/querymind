import { Navigate, Outlet, useLocation } from "react-router-dom";
import { LoadingIndicator } from "@/components/LoadingIndicator";
import { useAuthStore } from "@/store/authStore";

/**
 * The authenticated-route gate (a layout route wrapping every non-public path via `<Outlet/>`).
 * `"idle"`/`"authenticating"` cover `App.tsx`'s startup `restoreSession()` call -- shown as a
 * brief loading state rather than an immediate redirect, so a valid persisted session doesn't
 * flash a login page before it's had a chance to restore. `"unauthenticated"` redirects to
 * `/login`, remembering the page the caller wanted (`LoginPage` reads `location.state.from` to
 * send them back after signing in).
 */
export function RequireAuth() {
  const status = useAuthStore((state) => state.status);
  const location = useLocation();

  if (status === "idle" || status === "authenticating") {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <LoadingIndicator label="Restoring your session..." size="lg" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}