import { describe, expect, it } from "vitest";
import { buildResponseFromCompletedEvent, buildResponseFromFailedEvent } from "@/utils/streamingDerivation";
import {
  businessAnswerFixture,
  pipelineCompletedEventFixture,
  pipelineFailedEventFixture,
  stageCompletedEventFixture,
  stageStartedEventFixture,
} from "@/tests/mocks/fixtures";

describe("buildResponseFromCompletedEvent", () => {
  it("sums stage_completed durations into total_latency_ms", () => {
    const response = buildResponseFromCompletedEvent(
      "How many orders?",
      [stageStartedEventFixture, stageCompletedEventFixture],
      pipelineCompletedEventFixture,
    );

    expect(response.statistics.total_latency_ms).toBe(80);
    expect(response.statistics.stage_timings).toEqual([{ stage: "nlu", latency_ms: 80 }]);
  });

  it("carries the business answer and derives execution_result from it", () => {
    const response = buildResponseFromCompletedEvent("q", [], pipelineCompletedEventFixture);

    expect(response.business_answer).toBe(businessAnswerFixture);
    expect(response.execution_result).toBe(businessAnswerFixture.execution_result);
    expect(response.status).toBe("success");
    expect(response.error).toBeNull();
  });

  it("leaves generated_sql/validation_result/repair_result null -- a stream never carries them", () => {
    const response = buildResponseFromCompletedEvent("q", [], pipelineCompletedEventFixture);

    expect(response.generated_sql).toBeNull();
    expect(response.validation_result).toBeNull();
    expect(response.repair_result).toBeNull();
  });

  it("marks repair_attempted/repair_performed true only when an sql_repair stage completed", () => {
    const repairCompleted = { ...stageCompletedEventFixture, pipeline_stage: "sql_repair" as const };
    const response = buildResponseFromCompletedEvent("q", [repairCompleted], pipelineCompletedEventFixture);

    expect(response.statistics.repair_attempted).toBe(true);
    expect(response.statistics.repair_performed).toBe(true);
  });
});

describe("buildResponseFromFailedEvent", () => {
  it("produces a failed, answer-less response carrying the failure's error message", () => {
    const response = buildResponseFromFailedEvent("q", [stageCompletedEventFixture], pipelineFailedEventFixture);

    expect(response.status).toBe("failed");
    expect(response.error).toBe("The question could not be understood.");
    expect(response.business_answer).toBeNull();
    expect(response.execution_result).toBeNull();
    expect(response.statistics.total_latency_ms).toBe(80);
  });
});