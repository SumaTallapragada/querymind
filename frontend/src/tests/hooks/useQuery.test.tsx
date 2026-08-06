import { beforeEach, describe, expect, it } from "vitest";
import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useAskQuestion } from "@/hooks/useQuery";
import { useQueryStore } from "@/store/queryStore";
import { renderHookWithProviders } from "@/tests/testUtils";
import { server } from "@/tests/mocks/server";
import { queryMindResponseFixture } from "@/tests/mocks/fixtures";

beforeEach(() => {
  useQueryStore.setState({
    question: "",
    mode: "direct",
    status: "idle",
    events: [],
    response: null,
    errorMessage: null,
    history: [],
  });
});

describe("useAskQuestion", () => {
  it("drives queryStore through running -> settled on a successful POST /query", async () => {
    const { result } = renderHookWithProviders(() => useAskQuestion());

    act(() => result.current.mutate("Who are our top 5 customers by revenue?"));

    await waitFor(() => expect(useQueryStore.getState().status).toBe("settled"));

    expect(useQueryStore.getState().response).toEqual(queryMindResponseFixture);
    expect(useQueryStore.getState().mode).toBe("direct");
  });

  it("drives queryStore to transport_error with a safe message on a failed request", async () => {
    server.use(
      http.post("/api/v1/query", () =>
        HttpResponse.json({ detail: "The question is empty.", error_type: "EmptyQuestionError" }, { status: 422 }),
      ),
    );

    const { result } = renderHookWithProviders(() => useAskQuestion());

    act(() => result.current.mutate(""));

    await waitFor(() => expect(useQueryStore.getState().status).toBe("transport_error"));

    expect(useQueryStore.getState().errorMessage).toBe("The question is empty.");
  });
});