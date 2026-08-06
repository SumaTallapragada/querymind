import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PipelineTimeline } from "@/components/PipelineTimeline";
import { deriveStageRowsFromTimings } from "@/utils/pipelineTimeline";

describe("PipelineTimeline", () => {
  it("renders one list item per row, labeled by stage", () => {
    const rows = deriveStageRowsFromTimings([{ stage: "nlu", latency_ms: 80 }]);
    render(<PipelineTimeline rows={rows} />);

    const list = screen.getByRole("list", { name: "Pipeline stage timeline" });
    expect(list).toBeInTheDocument();
    expect(screen.getByText("NLU")).toBeInTheDocument();
  });

  it("shows formatted latency for a completed stage and none for a skipped one", () => {
    const rows = deriveStageRowsFromTimings([{ stage: "nlu", latency_ms: 842 }]);
    render(<PipelineTimeline rows={rows} />);

    expect(screen.getByText("842 ms")).toBeInTheDocument();
  });

  it("formats latency over a second in seconds", () => {
    const rows = deriveStageRowsFromTimings([{ stage: "nlu", latency_ms: 1500 }]);
    render(<PipelineTimeline rows={rows} />);

    expect(screen.getByText("1.50 s")).toBeInTheDocument();
  });
});