import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { DashboardPage } from "@/pages/Dashboard";
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

describe("DashboardPage", () => {
  it("shows the question form and no pipeline timeline before any question is asked", () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByRole("form", { name: "Ask QueryMind a question" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Pipeline stage timeline" })).not.toBeInTheDocument();
    expect(screen.getByText("No answer yet -- ask a question above.")).toBeInTheDocument();
  });

  it("renders the timeline, answer, and tabbed detail panels once a response has settled", () => {
    useQueryStore.getState().beginQuery(queryMindResponseFixture.original_question);
    useQueryStore.getState().succeed(queryMindResponseFixture);

    renderWithProviders(<DashboardPage />);

    expect(screen.getByRole("list", { name: "Pipeline stage timeline" })).toBeInTheDocument();
    expect(screen.getByText(queryMindResponseFixture.business_answer!.summary.title)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "SQL" })).toBeInTheDocument();
  });

  it("shows the error banner when the session ended in a transport error", () => {
    useQueryStore.getState().beginQuery("q");
    useQueryStore.getState().fail("The connection dropped.");

    renderWithProviders(<DashboardPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("The connection dropped.");
  });
});