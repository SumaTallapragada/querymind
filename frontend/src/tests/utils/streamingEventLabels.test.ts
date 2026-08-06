import { describe, expect, it } from "vitest";
import { describeEvent, formatEventTimestamp } from "@/utils/streamingEventLabels";
import {
  pipelineCompletedEventFixture,
  pipelineFailedEventFixture,
  pipelineStartedEventFixture,
  stageCompletedEventFixture,
  stageFailedEventFixture,
  stageStartedEventFixture,
} from "@/tests/mocks/fixtures";

describe("describeEvent", () => {
  it("describes every event type in plain, human-readable English", () => {
    expect(describeEvent(pipelineStartedEventFixture)).toBe("Pipeline started");
    expect(describeEvent(stageStartedEventFixture)).toBe("NLU started");
    expect(describeEvent(stageCompletedEventFixture)).toBe("NLU completed");
    expect(describeEvent(stageFailedEventFixture)).toBe("Validation failed");
    expect(describeEvent(pipelineCompletedEventFixture)).toBe("Pipeline completed");
    expect(describeEvent(pipelineFailedEventFixture)).toBe("Pipeline failed");
  });

  it("distinguishes a pipeline_completed event whose own status is failed", () => {
    const failedButCompleted = {
      ...pipelineCompletedEventFixture,
      payload: { ...pipelineCompletedEventFixture.payload, status: "failed" as const },
    };
    expect(describeEvent(failedButCompleted)).toBe("Pipeline completed (failed)");
  });
});

describe("formatEventTimestamp", () => {
  it("formats a valid ISO timestamp as a 24-hour time", () => {
    expect(formatEventTimestamp("2026-08-06T12:00:00.000Z")).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });

  it("passes an unparseable timestamp through unchanged rather than showing 'Invalid Date'", () => {
    expect(formatEventTimestamp("not-a-timestamp")).toBe("not-a-timestamp");
  });
});