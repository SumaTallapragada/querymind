import { NavLink } from "react-router-dom";
import { BarChart3, HeartPulse, LayoutDashboard, Settings, Stethoscope, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/store/uiStore";
import { useAuthStore } from "@/store/authStore";
import { roleSatisfies } from "@/utils/roles";
import { Button } from "@/components/ui";
import type { UserRole } from "@/models";

/** `minRole` mirrors the backend RBAC table (README §Authorization) -- kept in sync by hand
 * since the frontend has no way to derive it from the API itself; a mismatch here is only ever
 * a UX inconvenience (an item shown that 403s, or hidden when it wouldn't have), never a
 * security gap, since the backend enforces its own floor regardless of what's rendered here.
 */
const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, minRole: "analyst" as UserRole },
  { to: "/diagnostics", label: "Diagnostics", icon: Stethoscope, end: false, minRole: "admin" as UserRole },
  { to: "/health", label: "Health", icon: HeartPulse, end: false, minRole: "viewer" as UserRole },
  { to: "/metrics", label: "Metrics", icon: BarChart3, end: false, minRole: "admin" as UserRole },
  { to: "/settings", label: "Settings", icon: Settings, end: false, minRole: "admin" as UserRole },
] as const;

export function Sidebar() {
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);
  const setSidebarOpen = useUiStore((state) => state.setSidebarOpen);
  const role = useAuthStore((state) => state.user?.role);
  const visibleNavItems = NAV_ITEMS.filter((item) => role && roleSatisfies(role, item.minRole));

  return (
    <>
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        aria-label="Primary"
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-card transition-transform lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-border px-4">
          <span className="text-sm font-semibold tracking-tight">QueryMind</span>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {visibleNavItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-3 text-xs text-muted-foreground">
          Phase 18 &middot; React Frontend
        </div>
      </aside>
    </>
  );
}
