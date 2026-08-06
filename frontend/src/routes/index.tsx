import { createBrowserRouter } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { DashboardPage } from "@/pages/Dashboard";
import { DiagnosticsPage } from "@/pages/Diagnostics";
import { HealthPage } from "@/pages/Health";
import { MetricsPage } from "@/pages/Metrics";
import { SettingsPage } from "@/pages/Settings";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "diagnostics", element: <DiagnosticsPage /> },
      { path: "health", element: <HealthPage /> },
      { path: "metrics", element: <MetricsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);
