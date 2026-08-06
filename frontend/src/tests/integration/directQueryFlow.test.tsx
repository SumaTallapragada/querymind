/** End-to-end (within the frontend) exercise of the direct `POST /query` path: type a question
 * into `QueryInput`, submit, and confirm `DashboardPage`'s timeline/answer/SQL panels update
 * from the MSW-mocked response -- the same wiring a real backend round trip would drive.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

describe("direct query flow", () => {
  it("asking a question renders the pipeline timeline, answer, and SQL once the backend responds", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await user.type(screen.getByLabelText("Question"), queryMindResponseFixture.original_question);
    await user.click(screen.getByRole("button", { name: "Ask QueryMind" }));

    await waitFor(() =>
      expect(screen.getByText(queryMindResponseFixture.business_answer!.summary.title)).toBeInTheDocument(),
    );

    expect(screen.getByRole("list", { name: "Pipeline stage timeline" })).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "SQL" }));
    expect(document.querySelector("code")).toHaveTextContent("SELECT customer_id");

    // Appears twice: once as an example-question button, once as the new QueryHistory entry.
    expect(screen.getAllByText(queryMindResponseFixture.original_question)).toHaveLength(2);
  });
});