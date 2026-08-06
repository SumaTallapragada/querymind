import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExecutionPanel } from "@/components/ExecutionPanel";
import { failedExecutionResultFixture, sqlExecutionResultFixture } from "@/tests/mocks/fixtures";

describe("ExecutionPanel", () => {
  it("shows a placeholder when no execution has run yet", () => {
    render(<ExecutionPanel executionResult={null} />);
    expect(screen.getByText("No execution has run yet.")).toBeInTheDocument();
  });

  it("shows the status, database, and dialect for a successful execution", () => {
    render(<ExecutionPanel executionResult={sqlExecutionResultFixture} />);

    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("querymind")).toBeInTheDocument();
    expect(screen.getByText("postgresql")).toBeInTheDocument();
  });

  it("shows the execution error's code and message when execution failed", () => {
    render(<ExecutionPanel executionResult={failedExecutionResultFixture} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("E_QUERY_FAILED")).toBeInTheDocument();
    expect(screen.getByText('relation "orders" does not exist')).toBeInTheDocument();
  });
});