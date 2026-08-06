import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useStreaming } from "@/hooks/useStreaming";
import { useQueryStore } from "@/store/queryStore";
import { useUiStore } from "@/store/uiStore";
import type { StreamHandlers } from "@/services/streaming";
import { pipelineCompletedEventFixture, pipelineFailedEventFixture, stageStartedEventFixture } from "@/tests/mocks/fixtures";

const stopSpy = vi.fn();
let capturedHandlers: StreamHandlers | null = null;

vi.mock("@/services/streaming", () => ({
  streamQuery: vi.fn((_transport: string, _question: string, handlers: StreamHandlers) => {
    capturedHandlers = handlers;
    return stopSpy;
  }),
}));

beforeEach(() => {
  capturedHandlers = null;
  stopSpy.mockClear();
  useQueryStore.setState({
    question: "",
    mode: "direct",
    status: "idle",
    events: [],
    response: null,
    errorMessage: null,
    history: [],
  });
  useUiStore.setState({ streamingTransport: "sse" });
});

describe("useStreaming", () => {
  it("start() switches to streaming mode and begins a running session", () => {
    const { result } = renderHook(() => useStreaming());

    act(() => result.current.start("Who are our top 5 customers?"));

    expect(useQueryStore.getState().mode).toBe("streaming");
    expect(useQueryStore.getState().status).toBe("running");
    expect(useQueryStore.getState().question).toBe("Who are our top 5 customers?");
  });

  it("forwards every received event into queryStore, in order", () => {
    const { result } = renderHook(() => useStreaming());
    act(() => result.current.start("q"));

    act(() => capturedHandlers?.onEvent(stageStartedEventFixture));

    expect(useQueryStore.getState().events).toEqual([stageStartedEventFixture]);
  });

  it("settles the session when a pipeline_completed event arrives", () => {
    const { result } = renderHook(() => useStreaming());
    act(() => result.current.start("q"));

    act(() => capturedHandlers?.onEvent(pipelineCompletedEventFixture));

    expect(useQueryStore.getState().status).toBe("settled");
    expect(useQueryStore.getState().response?.status).toBe("success");
  });

  it("settles (not fails) the session when a pipeline_failed event arrives -- a well-formed response still came back", () => {
    const { result } = renderHook(() => useStreaming());
    act(() => result.current.start("q"));

    act(() => capturedHandlers?.onEvent(pipelineFailedEventFixture));

    expect(useQueryStore.getState().status).toBe("settled");
    expect(useQueryStore.getState().response?.status).toBe("failed");
  });

  it("stop() closes the connection and returns a running session to idle", () => {
    const { result } = renderHook(() => useStreaming());
    act(() => result.current.start("q"));

    act(() => result.current.stop());

    expect(stopSpy).toHaveBeenCalled();
    expect(useQueryStore.getState().status).toBe("idle");
  });
});