import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StreamingEvents } from "@/components/StreamingEvents";
import { pipelineStartedEventFixture, stageCompletedEventFixture, stageStartedEventFixture } from "@/tests/mocks/fixtures";

describe("StreamingEvents", () => {
  it("shows an empty message when there are no events yet", () => {
    render(<StreamingEvents events={[]} />);
    expect(screen.getByText("No streaming events yet.")).toBeInTheDocument();
  });

  it("supports a custom empty message", () => {
    render(<StreamingEvents events={[]} emptyMessage="Nothing yet." />);
    expect(screen.getByText("Nothing yet.")).toBeInTheDocument();
  });

  it("renders one live-region entry per event, in arrival order", () => {
    render(<StreamingEvents events={[pipelineStartedEventFixture, stageStartedEventFixture, stageCompletedEventFixture]} />);

    const list = screen.getByRole("list", { name: "Streaming events" });
    const items = list.querySelectorAll("li");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Pipeline started");
    expect(items[1]).toHaveTextContent("NLU started");
    expect(items[2]).toHaveTextContent("NLU completed");
  });
});