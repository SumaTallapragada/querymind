import { CheckCircle2, Circle, Loader2, MinusCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { StageRow, StageRowStatus } from "@/utils/pipelineTimeline";

export interface PipelineTimelineProps {
  rows: StageRow[];
}

const STATUS_ICON: Record<StageRowStatus, typeof Circle> = {
  pending: Circle,
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  skipped: MinusCircle,
};

const STATUS_COLOR: Record<StageRowStatus, string> = {
  pending: "text-muted-foreground",
  running: "text-primary",
  completed: "text-success",
  failed: "text-destructive",
  skipped: "text-muted-foreground/50",
};

const STATUS_LABEL: Record<StageRowStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  skipped: "Skipped",
};

function formatLatency(latencyMs: number | null): string {
  if (latencyMs === null) return "";
  return latencyMs < 1000 ? `${latencyMs.toFixed(0)} ms` : `${(latencyMs / 1000).toFixed(2)} s`;
}

/** Visualizes every pipeline stage's status/latency -- fed either a completed response's
 * `stage_timings` or a live stream's accumulated events (see `utils/pipelineTimeline.ts`), so
 * it renders identically for both.
 */
export function PipelineTimeline({ rows }: PipelineTimelineProps) {
  return (
    <ol aria-label="Pipeline stage timeline" className="flex flex-col gap-1">
      {rows.map((row) => {
        const Icon = STATUS_ICON[row.status];
        return (
          <li key={row.stage} className="flex items-center gap-3 rounded-md px-2 py-1.5">
            <Icon
              className={cn("h-4 w-4 shrink-0", STATUS_COLOR[row.status], row.status === "running" && "animate-spin")}
              aria-hidden="true"
            />
            <span className={cn("flex-1 text-sm", row.status === "skipped" && "text-muted-foreground/60")}>
              {row.label}
            </span>
            <span className="sr-only">{STATUS_LABEL[row.status]}</span>
            {row.latencyMs !== null && (
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {formatLatency(row.latencyMs)}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
