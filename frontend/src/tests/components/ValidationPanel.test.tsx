import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ValidationPanel } from "@/components/ValidationPanel";
import { invalidValidationResultFixture, sqlValidationResultFixture } from "@/tests/mocks/fixtures";

describe("ValidationPanel", () => {
  it("explains why validation is unavailable in streaming mode when null", () => {
    render(<ValidationPanel validationResult={null} />);
    expect(screen.getByText(/No validation result available/)).toBeInTheDocument();
  });

  it("shows a Valid badge and any warnings for a passing result", () => {
    render(<ValidationPanel validationResult={sqlValidationResultFixture} />);

    expect(screen.getByText("Valid")).toBeInTheDocument();
    expect(screen.getByText(/Warnings \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("W_IMPLICIT_CAST")).toBeInTheDocument();
  });

  it("shows an Invalid badge and every error for a failing result", () => {
    render(<ValidationPanel validationResult={invalidValidationResultFixture} />);

    expect(screen.getByText("Invalid")).toBeInTheDocument();
    expect(screen.getByText(/Errors \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("E_UNKNOWN_TABLE")).toBeInTheDocument();
    expect(screen.getByText("Table 'custmers' does not exist.")).toBeInTheDocument();
  });
});