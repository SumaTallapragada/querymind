import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveTheme, useUiStore } from "@/store/uiStore";

afterEach(() => {
  useUiStore.setState({ theme: "system", sidebarOpen: false, streamingTransport: "sse" });
});

describe("useUiStore", () => {
  it("defaults to system theme, a closed sidebar, and SSE transport", () => {
    const state = useUiStore.getState();
    expect(state.theme).toBe("system");
    expect(state.sidebarOpen).toBe(false);
    expect(state.streamingTransport).toBe("sse");
  });

  it("toggleSidebar flips sidebarOpen", () => {
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarOpen).toBe(true);
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarOpen).toBe(false);
  });

  it("setTheme and setStreamingTransport set the given value directly", () => {
    useUiStore.getState().setTheme("dark");
    expect(useUiStore.getState().theme).toBe("dark");

    useUiStore.getState().setStreamingTransport("websocket");
    expect(useUiStore.getState().streamingTransport).toBe("websocket");
  });
});

describe("resolveTheme", () => {
  it("passes light/dark through unchanged", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("resolves 'system' against window.matchMedia's dark-mode preference", () => {
    const matchMediaSpy = vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true,
    } as MediaQueryList);

    expect(resolveTheme("system")).toBe("dark");

    matchMediaSpy.mockReturnValue({ matches: false } as MediaQueryList);
    expect(resolveTheme("system")).toBe("light");

    matchMediaSpy.mockRestore();
  });
});