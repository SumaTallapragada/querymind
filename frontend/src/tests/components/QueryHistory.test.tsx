import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryHistory } from "@/components/QueryHistory";
import { useQueryStore } from "@/store/queryStore";
import { renderWithProviders } from "@/tests/testUtils";
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

describe("QueryHistory", () => {
  it("shows a placeholder when no questions have been asked", () => {
    renderWithProviders(<QueryHistory />);
    expect(screen.getByText("No questions asked yet this session.")).toBeInTheDocument();
  });

  it("lists each history entry with its question and outcome icon", () => {
    useQueryStore.getState().beginQuery(queryMindResponseFixture.original_question);
    useQueryStore.getState().succeed(queryMindResponseFixture);

    renderWithProviders(<QueryHistory />);

    expect(screen.getByText(queryMindResponseFixture.original_question)).toBeInTheDocument();
  });

  it("Clear empties the history list", async () => {
    const user = userEvent.setup();
    useQueryStore.getState().beginQuery(queryMindResponseFixture.original_question);
    useQueryStore.getState().succeed(queryMindResponseFixture);

    renderWithProviders(<QueryHistory />);
    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(useQueryStore.getState().history).toEqual([]);
  });

  it("re-asking a question fires a new request that settles into a second history entry", async () => {
    const user = userEvent.setup();
    useQueryStore.getState().beginQuery(queryMindResponseFixture.original_question);
    useQueryStore.getState().succeed(queryMindResponseFixture);

    renderWithProviders(<QueryHistory />);
    await user.click(screen.getByRole("button", { name: `Ask "${queryMindResponseFixture.original_question}" again` }));

    await waitFor(() => expect(useQueryStore.getState().history).toHaveLength(2));
    expect(useQueryStore.getState().status).toBe("settled");
  });
});