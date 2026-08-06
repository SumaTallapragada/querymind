import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DiagnosticsPage } from "@/pages/Diagnostics";
import { renderWithProviders } from "@/tests/testUtils";

describe("DiagnosticsPage", () => {
  it("shows every finding once loaded", async () => {
    renderWithProviders(<DiagnosticsPage />);

    await waitFor(() => expect(screen.getByText("database connectivity")).toBeInTheDocument());
    expect(screen.getByText("llm api key")).toBeInTheDocument();
  });

  it("filters findings by status", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DiagnosticsPage />);
    await waitFor(() => expect(screen.getByText("database connectivity")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Warning" }));

    expect(screen.queryByText("database connectivity")).not.toBeInTheDocument();
    expect(screen.getByText("llm api key")).toBeInTheDocument();
  });

  it("filters findings by a search term", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DiagnosticsPage />);
    await waitFor(() => expect(screen.getByText("database connectivity")).toBeInTheDocument());

    await user.type(screen.getByLabelText("Search diagnostic checks"), "connectivity");

    expect(screen.getByText("database connectivity")).toBeInTheDocument();
    expect(screen.queryByText("llm api key")).not.toBeInTheDocument();
  });
});