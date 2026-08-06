/**
 * UI-only state -- never server data. Anything derived from a backend response belongs in
 * TanStack Query (`hooks/`) or `queryStore.ts`'s streaming session state instead; this store
 * holds only what the *interface itself* is doing: theme, sidebar, and which streaming
 * transport a user has chosen to demonstrate.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { StreamingTransport } from "@/models";

export type Theme = "light" | "dark" | "system";

interface UiState {
  theme: Theme;
  sidebarOpen: boolean;
  streamingTransport: StreamingTransport;
  setTheme: (theme: Theme) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setStreamingTransport: (transport: StreamingTransport) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: "system",
      sidebarOpen: false,
      streamingTransport: "sse",
      setTheme: (theme) => set({ theme }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setStreamingTransport: (transport) => set({ streamingTransport: transport }),
    }),
    { name: "querymind-ui" },
  ),
);

/** Resolve `"system"` against the OS preference; `"light"`/`"dark"` pass through unchanged. */
export function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
