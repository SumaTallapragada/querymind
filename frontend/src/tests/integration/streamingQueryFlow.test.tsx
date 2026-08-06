/** End-to-end (within the frontend) exercise of the streaming path: switch `QueryInput` to
 * streaming mode, submit, and drive a fake `streamQuery` through a realistic event sequence,
 * confirming `StreamingEvents`/`PipelineTimeline`/`AnswerCard` all update live as events arrive
 * -- exactly as they would from a real SSE/WebSocket connection (rule 4 of the Phase 18 spec:
 * the backend decides the event sequence, the frontend only renders it).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DashboardPage } from "@/pages/Dashboard";
import { useQueryStore } from "@/store/queryStore";
import { useUiStore } from "@/store/uiStore";
import { renderWithProviders } from "@/tests/testUtils";
import type { StreamHandlers } from "@/services/streaming";
import {
  pipelineCompletedEventFixture,
  pipelineStartedEventFixture,
  stageCompletedEventFixture,
  stageStartedEventFixture,
} from "@/tests/mocks/fixtures";

let capturedHandlers: StreamHandlers | null = null;

vi.mock("@/services/streaming", () => ({
  streamQuery: vi.fn((_transport: string, _question: string, handlers: StreamHandlers) => {
    capturedHandlers = handlers;
    return vi.fn();
  }),
}));

beforeEach(() => {
  capturedHandlers = null;
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

describe("streaming query flow", () => {
  it("renders each event as it arrives, then the final answer once pipeline_completed fires", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await user.click(screen.getByRole("tab", { name: "Streaming" }));
    await user.type(screen.getByLabelText("Question"), pipelineStartedEventFixture.payload.original_question);
    await user.click(screen.getByRole("button", { name: "Ask QueryMind" }));

    await waitFor(() => expect(capturedHandlers).not.toBeNull());

    act(() => capturedHandlers?.onEvent(pipelineStartedEventFixture));
    expect(screen.getByText("Pipeline started")).toBeInTheDocument();

    act(() => capturedHandlers?.onEvent(stageStartedEventFixture));
    act(() => capturedHandlers?.onEvent(stageCompletedEventFixture));
    expect(screen.getByText("NLU completed")).toBeInTheDocument();

    act(() => capturedHandlers?.onEvent(pipelineCompletedEventFixture));

    expect(useQueryStore.getState().status).toBe("settled");
    expect(
      screen.getByText(pipelineCompletedEventFixture.payload.business_answer!.summary.title),
    ).toBeInTheDocument();
  });

  it("Cancel stops the stream and returns the session to idle", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await user.click(screen.getByRole("tab", { name: "Streaming" }));
    await user.type(screen.getByLabelText("Question"), "q");
    await user.click(screen.getByRole("button", { name: "Ask QueryMind" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(useQueryStore.getState().status).toBe("idle");
  });
});