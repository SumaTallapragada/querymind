import { createBrowserRouter } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RequireAuth, RequireRole } from "@/components/Auth";
import { LoginPage } from "@/pages/Login";
import { DashboardPage } from "@/pages/Dashboard";
import { DiagnosticsPage } from "@/pages/Diagnostics";
import { HealthPage } from "@/pages/Health";
import { MetricsPage } from "@/pages/Metrics";
import { SettingsPage } from "@/pages/Settings";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        path: "/",
        element: <Layout />,
        children: [
          {
            index: true,
            element: (
              <RequireRole minRole="analyst">
                <DashboardPage />
              </RequireRole>
            ),
          },
          {
            path: "diagnostics",
            element: (
              <RequireRole minRole="admin">
                <DiagnosticsPage />
              </RequireRole>
            ),
          },
          // Any authenticated role -- matches `GET /health` requiring `CurrentUser` (no role floor).
          { path: "health", element: <HealthPage /> },
          {
            path: "metrics",
            element: (
              <RequireRole minRole="admin">
                <MetricsPage />
              </RequireRole>
            ),
          },
          {
            path: "settings",
            element: (
              <RequireRole minRole="admin">
                <SettingsPage />
              </RequireRole>
            ),
          },
        ],
      },
    ],
  },
]);