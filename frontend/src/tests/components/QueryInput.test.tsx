import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryInput } from "@/components/QueryInput";
import { useQueryStore } from "@/store/queryStore";
import { useUiStore } from "@/store/uiStore";
import { renderWithProviders } from "@/tests/testUtils";

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
  useUiStore.setState({ streamingTransport: "sse" });
});

describe("QueryInput", () => {
  it("shows a validation error and does not submit when the question is empty", async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryInput />);

    await user.click(screen.getByRole("button", { name: "Ask QueryMind" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a question.");
    expect(useQueryStore.getState().status).toBe("idle");
  });

  it("fills the question field when an example question is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryInput />);

    await user.click(screen.getByRole("button", { name: "Who are our top 5 customers by revenue?" }));

    expect(screen.getByLabelText("Question")).toHaveValue("Who are our top 5 customers by revenue?");
  });

  it("submits a direct question and drives the session to settled", async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryInput />);

    await user.type(screen.getByLabelText("Question"), "How many orders were placed today?");
    await user.click(screen.getByRole("button", { name: "Ask QueryMind" }));

    await waitFor(() => expect(useQueryStore.getState().status).toBe("settled"));
  });

  it("shows a transport picker only in streaming mode", async () => {
    const user = userEvent.setup();
    renderWithProviders(<QueryInput />);

    expect(screen.queryByLabelText("Transport")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Streaming" }));

    expect(screen.getByLabelText("Transport")).toBeInTheDocument();
  });
});