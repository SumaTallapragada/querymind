import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { resolveTheme, useUiStore } from "@/store/uiStore";

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/diagnostics": "Diagnostics",
  "/health": "Health",
  "/metrics": "Metrics",
  "/settings": "Settings",
};

function useThemeSync(): void {
  const theme = useUiStore((state) => state.theme);
  useEffect(() => {
    const root = document.documentElement;
    const apply = () => root.classList.toggle("dark", resolveTheme(theme) === "dark");
    apply();
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
}

export function Layout() {
  useThemeSync();
  const location = useLocation();
  const title = PAGE_TITLES[location.pathname] ?? "QueryMind";

  return (
    <div className="flex h-svh overflow-hidden bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar title={title} />
        <main id="main-content" className="flex-1 overflow-y-auto p-4 lg:p-6">
          <ErrorBoundary section={title}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
