import { PIPELINE_STAGE_LABELS, type PipelineEvent } from "@/models";

/** A short, human-readable label for one `PipelineEvent` -- e.g. "SQL Generation completed". */
export function describeEvent(event: PipelineEvent): string {
  switch (event.event_type) {
    case "pipeline_started":
      return "Pipeline started";
    case "stage_started":
      return `${PIPELINE_STAGE_LABELS[event.pipeline_stage]} started`;
    case "stage_completed":
      return `${PIPELINE_STAGE_LABELS[event.pipeline_stage]} completed`;
    case "stage_failed":
      return `${PIPELINE_STAGE_LABELS[event.pipeline_stage]} failed`;
    case "pipeline_completed":
      return event.payload.status === "success" ? "Pipeline completed" : "Pipeline completed (failed)";
    case "pipeline_failed":
      return "Pipeline failed";
    case "heartbeat":
      return "Heartbeat";
    case "client_disconnected":
      return "Client disconnected";
  }
}

export function formatEventTimestamp(isoTimestamp: string): string {
  const date = new Date(isoTimestamp);
  if (Number.isNaN(date.getTime())) return isoTimestamp;
  return date.toLocaleTimeString(undefined, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
