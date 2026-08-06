import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useClipboard } from "@/hooks/useClipboard";

describe("useClipboard", () => {
  it("writes the given text to the clipboard and reports copied", async () => {
    const { result } = renderHook(() => useClipboard());

    expect(result.current.copied).toBe(false);

    await act(async () => {
      await result.current.copy("SELECT 1");
    });

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("SELECT 1");
    expect(result.current.copied).toBe(true);
  });

  it("resets copied back to false after the reset delay", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useClipboard());

    await act(async () => {
      await result.current.copy("SELECT 1");
    });
    expect(result.current.copied).toBe(true);

    act(() => vi.advanceTimersByTime(1500));

    expect(result.current.copied).toBe(false);
    vi.useRealTimers();
  });
});