import { useEffect, useRef } from "react";
import { AlertCircle, CheckCircle2, Info, PlayCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui";
import { describeEvent, formatEventTimestamp } from "@/utils/streamingEventLabels";
import type { PipelineEvent, PipelineEventType } from "@/models";

export interface StreamingEventsProps {
  events: PipelineEvent[];
  emptyMessage?: string;
}

const EVENT_ICON: Record<PipelineEventType, typeof Info> = {
  pipeline_started: PlayCircle,
  stage_started: Info,
  stage_completed: CheckCircle2,
  stage_failed: XCircle,
  pipeline_completed: CheckCircle2,
  pipeline_failed: XCircle,
  heartbeat: AlertCircle,
  client_disconnected: AlertCircle,
};

const EVENT_COLOR: Record<PipelineEventType, string> = {
  pipeline_started: "text-primary",
  stage_started: "text-muted-foreground",
  stage_completed: "text-success",
  stage_failed: "text-destructive",
  pipeline_completed: "text-success",
  pipeline_failed: "text-destructive",
  heartbeat: "text-muted-foreground",
  client_disconnected: "text-warning",
};

/** A live, timestamped feed of every `PipelineEvent` received so far -- purely a rendering of
 * what the backend sent, in arrival order (rule 4 of the Phase 18 spec).
 */
export function StreamingEvents({ events, emptyMessage = "No streaming events yet." }: StreamingEventsProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [events.length]);

  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }

  return (
    <ScrollArea className="h-64 rounded-md border border-border">
      <ul aria-live="polite" aria-label="Streaming events" className="flex flex-col divide-y divide-border">
        {events.map((event) => {
          const Icon = EVENT_ICON[event.event_type];
          return (
            <li key={event.event_id} className="flex items-center gap-2.5 px-3 py-2 text-sm">
              <Icon className={cn("h-3.5 w-3.5 shrink-0", EVENT_COLOR[event.event_type])} aria-hidden="true" />
              <span className="flex-1">{describeEvent(event)}</span>
              <time
                dateTime={event.timestamp}
                className="font-mono text-xs tabular-nums text-muted-foreground"
              >
                {formatEventTimestamp(event.timestamp)}
              </time>
            </li>
          );
        })}
      </ul>
      <div ref={bottomRef} />
    </ScrollArea>
  );
}
