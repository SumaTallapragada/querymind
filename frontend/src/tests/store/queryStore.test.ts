import { beforeEach, describe, expect, it } from "vitest";
import { useQueryStore } from "@/store/queryStore";
import { queryMindResponseFixture, stageStartedEventFixture } from "@/tests/mocks/fixtures";

function resetStore(): void {
  useQueryStore.setState({
    question: "",
    mode: "direct",
    status: "idle",
    events: [],
    response: null,
    errorMessage: null,
    history: [],
  });
}

beforeEach(resetStore);

describe("useQueryStore", () => {
  it("beginQuery moves to running and clears any prior response/events/error", () => {
    useQueryStore.setState({ response: queryMindResponseFixture, errorMessage: "old error", events: [stageStartedEventFixture] });

    useQueryStore.getState().beginQuery("New question?");

    const state = useQueryStore.getState();
    expect(state.status).toBe("running");
    expect(state.question).toBe("New question?");
    expect(state.response).toBeNull();
    expect(state.errorMessage).toBeNull();
    expect(state.events).toEqual([]);
  });

  it("appendEvent accumulates events in arrival order", () => {
    useQueryStore.getState().appendEvent(stageStartedEventFixture);
    useQueryStore.getState().appendEvent(stageStartedEventFixture);

    expect(useQueryStore.getState().events).toHaveLength(2);
  });

  it("succeed settles the session and records a history entry with the response's own status", () => {
    useQueryStore.getState().beginQuery(queryMindResponseFixture.original_question);

    useQueryStore.getState().succeed(queryMindResponseFixture);

    const state = useQueryStore.getState();
    expect(state.status).toBe("settled");
    expect(state.response).toBe(queryMindResponseFixture);
    expect(state.history).toHaveLength(1);
    expect(state.history[0]).toMatchObject({
      question: queryMindResponseFixture.original_question,
      status: "success",
      totalLatencyMs: queryMindResponseFixture.statistics.total_latency_ms,
    });
  });

  it("fail moves to transport_error and records a failed history entry with null latency", () => {
    useQueryStore.getState().beginQuery("bad question");

    useQueryStore.getState().fail("The connection dropped.");

    const state = useQueryStore.getState();
    expect(state.status).toBe("transport_error");
    expect(state.errorMessage).toBe("The connection dropped.");
    expect(state.history[0]).toMatchObject({ status: "failed", totalLatencyMs: null });
  });

  it("caps history at 50 entries, dropping the oldest", () => {
    for (let i = 0; i < 55; i += 1) {
      useQueryStore.getState().beginQuery(`q${i}`);
      useQueryStore.getState().succeed(queryMindResponseFixture);
    }

    const history = useQueryStore.getState().history;
    expect(history).toHaveLength(50);
    expect(history[0]?.question).toBe("q54"); // most recent first
    expect(history.some((entry) => entry.question === "q0")).toBe(false); // oldest dropped
  });

  it("clearHistory empties history without touching the current session", () => {
    useQueryStore.getState().beginQuery("q");
    useQueryStore.getState().succeed(queryMindResponseFixture);

    useQueryStore.getState().clearHistory();

    expect(useQueryStore.getState().history).toEqual([]);
    expect(useQueryStore.getState().status).toBe("settled");
  });

  it("reset returns the session to idle without touching history", () => {
    useQueryStore.getState().beginQuery("q");
    useQueryStore.getState().succeed(queryMindResponseFixture);

    useQueryStore.getState().reset();

    const state = useQueryStore.getState();
    expect(state.status).toBe("idle");
    expect(state.response).toBeNull();
    expect(state.history).toHaveLength(1);
  });
});