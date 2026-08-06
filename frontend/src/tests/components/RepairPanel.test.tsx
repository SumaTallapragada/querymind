import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RepairPanel } from "@/components/RepairPanel";
import { sqlRepairResultFixture } from "@/tests/mocks/fixtures";

describe("RepairPanel", () => {
  it("explains repair never ran when null", () => {
    render(<RepairPanel repairResult={null} />);
    expect(screen.getByText(/Repair never ran for this question/)).toBeInTheDocument();
  });

  it("shows the repair status badge and one row per attempt", () => {
    render(<RepairPanel repairResult={sqlRepairResultFixture} />);

    expect(screen.getByText("Repaired")).toBeInTheDocument();
    expect(screen.getByText("Attempt 1")).toBeInTheDocument();
    expect(screen.getByText("unknown table")).toBeInTheDocument();
    expect(screen.getByText("Repaired SQL validated successfully.")).toBeInTheDocument();
  });
});