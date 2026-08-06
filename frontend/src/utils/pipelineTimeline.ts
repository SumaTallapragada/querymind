/** Pure derivation of per-stage timeline rows -- no orchestration, just reshaping numbers the
 * backend already computed (either a completed response's `stage_timings`, or a live stream's
 * accumulated `stage_started`/`stage_completed`/`stage_failed` events) into one shape
 * `PipelineTimeline` can render regardless of which mode produced it.
 */

import {
  PIPELINE_STAGES,
  PIPELINE_STAGE_LABELS,
  type PipelineEvent,
  type PipelineStage,
  type StageTiming,
} from "@/models";

export type StageRowStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export interface StageRow {
  stage: PipelineStage;
  label: string;
  status: StageRowStatus;
  latencyMs: number | null;
}

export function deriveStageRowsFromEvents(events: PipelineEvent[], isTerminal: boolean): StageRow[] {
  return PIPELINE_STAGES.map((stage) => {
    const failed = events.find(
      (event) => event.event_type === "stage_failed" && event.pipeline_stage === stage,
    );
    const completed = events.find(
      (event) => event.event_type === "stage_completed" && event.pipeline_stage === stage,
    );
    const started = events.find(
      (event) => event.event_type === "stage_started" && event.pipeline_stage === stage,
    );

    if (failed && failed.event_type === "stage_failed") {
      return { stage, label: PIPELINE_STAGE_LABELS[stage], status: "failed", latencyMs: failed.payload.duration_ms };
    }
    if (completed && completed.event_type === "stage_completed") {
      return {
        stage,
        label: PIPELINE_STAGE_LABELS[stage],
        status: "completed",
        latencyMs: completed.payload.duration_ms,
      };
    }
    if (started) {
      return { stage, label: PIPELINE_STAGE_LABELS[stage], status: "running", latencyMs: null };
    }
    return {
      stage,
      label: PIPELINE_STAGE_LABELS[stage],
      status: isTerminal ? "skipped" : "pending",
      latencyMs: null,
    };
  });
}

export function deriveStageRowsFromTimings(stageTimings: StageTiming[]): StageRow[] {
  return PIPELINE_STAGES.map((stage) => {
    const timing = stageTimings.find((entry) => entry.stage === stage);
    if (timing) {
      return { stage, label: PIPELINE_STAGE_LABELS[stage], status: "completed", latencyMs: timing.latency_ms };
    }
    return { stage, label: PIPELINE_STAGE_LABELS[stage], status: "skipped", latencyMs: null };
  });
}
