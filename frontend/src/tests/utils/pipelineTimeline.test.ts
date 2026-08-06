import { describe, expect, it } from "vitest";
import { deriveStageRowsFromEvents, deriveStageRowsFromTimings } from "@/utils/pipelineTimeline";
import { PIPELINE_STAGES } from "@/models";
import { stageCompletedEventFixture, stageFailedEventFixture, stageStartedEventFixture } from "@/tests/mocks/fixtures";

describe("deriveStageRowsFromEvents", () => {
  it("returns one row per pipeline stage, in stage order", () => {
    const rows = deriveStageRowsFromEvents([], false);
    expect(rows.map((row) => row.stage)).toEqual([...PIPELINE_STAGES]);
  });

  it("marks a stage completed with its duration when a stage_completed event exists", () => {
    const rows = deriveStageRowsFromEvents([stageCompletedEventFixture], false);
    const nlu = rows.find((row) => row.stage === "nlu")!;
    expect(nlu.status).toBe("completed");
    expect(nlu.latencyMs).toBe(80);
  });

  it("marks a stage failed even if it also has a stage_started event", () => {
    const rows = deriveStageRowsFromEvents(
      [{ ...stageStartedEventFixture, pipeline_stage: "sql_validation" }, stageFailedEventFixture],
      false,
    );
    const validation = rows.find((row) => row.stage === "sql_validation")!;
    expect(validation.status).toBe("failed");
    expect(validation.latencyMs).toBe(12);
  });

  it("marks a started-but-not-completed stage running", () => {
    const rows = deriveStageRowsFromEvents([stageStartedEventFixture], false);
    const nlu = rows.find((row) => row.stage === "nlu")!;
    expect(nlu.status).toBe("running");
    expect(nlu.latencyMs).toBeNull();
  });

  it("marks an untouched stage pending while the stream is live, skipped once terminal", () => {
    const liveRows = deriveStageRowsFromEvents([], false);
    expect(liveRows.every((row) => row.status === "pending")).toBe(true);

    const terminalRows = deriveStageRowsFromEvents([], true);
    expect(terminalRows.every((row) => row.status === "skipped")).toBe(true);
  });
});

describe("deriveStageRowsFromTimings", () => {
  it("marks every timed stage completed and every other stage skipped", () => {
    const rows = deriveStageRowsFromTimings([{ stage: "nlu", latency_ms: 80 }]);

    expect(rows.find((row) => row.stage === "nlu")).toMatchObject({ status: "completed", latencyMs: 80 });
    expect(rows.find((row) => row.stage === "sql_execution")).toMatchObject({ status: "skipped", latencyMs: null });
  });
});