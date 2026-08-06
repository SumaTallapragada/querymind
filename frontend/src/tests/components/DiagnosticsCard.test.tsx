import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiagnosticsCard } from "@/components/DiagnosticsCard";
import { diagnosticsReportFixture } from "@/tests/mocks/fixtures";

describe("DiagnosticsCard", () => {
  it("renders a pass finding with a humanized name and status badge", () => {
    render(<DiagnosticsCard finding={diagnosticsReportFixture.findings[0]!} />);

    expect(screen.getByText("database connectivity")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("Connected.")).toBeInTheDocument();
  });

  it("renders a warning finding's details when present", () => {
    render(<DiagnosticsCard finding={diagnosticsReportFixture.findings[1]!} />);

    expect(screen.getByText("WARNING")).toBeInTheDocument();
    expect(screen.getByText("env=development")).toBeInTheDocument();
  });
});