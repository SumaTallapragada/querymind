/**
 * Reshapes an accumulated stream of `PipelineEvent`s into a `QueryMindResponse`-shaped object,
 * for components (`PipelineTimeline`, `SQLViewer`, `ResultTable`, ...) built to render
 * `POST /query`'s response either way. This is pure data reshaping, not orchestration or
 * business logic: every number and value here already came from the backend, in some earlier
 * event -- nothing is computed, inferred, or generated.
 *
 * `pipeline_completed`'s own payload only carries `status`/`error`/`business_answer` (see
 * `querymind.streaming.models.PipelineCompletedEvent`) -- unlike a direct `POST /query` call,
 * a streamed run never gives the frontend a standalone `generated_sql`/`validation_result`/
 * `repair_result`; those stay `null` here. `SQLViewer`/`ValidationPanel`/`RepairPanel` degrade
 * gracefully when they're absent (see each component's own empty state).
 */

import type {
  PipelineCompletedEvent,
  PipelineEvent,
  PipelineFailedEvent,
  PipelineStatistics,
  QueryMindResponse,
  StageCompletedEvent,
  StageTiming,
} from "@/models";

function deriveStatistics(events: PipelineEvent[]): PipelineStatistics {
  const stageTimings: StageTiming[] = events
    .filter((event): event is StageCompletedEvent => event.event_type === "stage_completed")
    .map((event) => ({ stage: event.pipeline_stage, latency_ms: event.payload.duration_ms }));

  const totalLatencyMs = stageTimings.reduce((sum, timing) => sum + timing.latency_ms, 0);
  const repairAttempted = stageTimings.some((timing) => timing.stage === "sql_repair");

  return {
    total_latency_ms: totalLatencyMs,
    stage_timings: stageTimings,
    repair_attempted: repairAttempted,
    repair_performed: repairAttempted,
  };
}

export function buildResponseFromCompletedEvent(
  question: string,
  events: PipelineEvent[],
  completed: PipelineCompletedEvent,
): QueryMindResponse {
  return {
    original_question: question,
    business_answer: completed.payload.business_answer,
    generated_sql: null,
    validation_result: null,
    repair_result: null,
    execution_result: completed.payload.business_answer?.execution_result ?? null,
    statistics: deriveStatistics(events),
    status: completed.payload.status,
    error: completed.payload.error,
  };
}

export function buildResponseFromFailedEvent(
  question: string,
  events: PipelineEvent[],
  failed: PipelineFailedEvent,
): QueryMindResponse {
  return {
    original_question: question,
    business_answer: null,
    generated_sql: null,
    validation_result: null,
    repair_result: null,
    execution_result: null,
    statistics: deriveStatistics(events),
    status: "failed",
    error: failed.payload.error_message,
  };
}
