/**
 * Mirrors `querymind.streaming.models` -- `PipelineEvent` and its nine subclasses. Every event
 * shares the same six top-level keys; `payload`'s shape depends on `event_type`, modeled here
 * as a discriminated union so a consumer never needs a type assertion to read `payload`.
 */

import type { BusinessAnswer } from "./resultFormatter";
import type { PipelineStage, PipelineStatus } from "./pipeline";

export type PipelineEventType =
  | "pipeline_started"
  | "stage_started"
  | "stage_completed"
  | "stage_failed"
  | "pipeline_completed"
  | "pipeline_failed"
  | "heartbeat"
  | "client_disconnected";

interface BaseEvent {
  event_id: string;
  correlation_id: string;
  timestamp: string;
  pipeline_stage: PipelineStage | null;
}

export interface PipelineStartedEvent extends BaseEvent {
  event_type: "pipeline_started";
  payload: { original_question: string };
}

export interface StageStartedEvent extends BaseEvent {
  event_type: "stage_started";
  pipeline_stage: PipelineStage;
  payload: Record<string, never>;
}

export interface StageCompletedEvent extends BaseEvent {
  event_type: "stage_completed";
  pipeline_stage: PipelineStage;
  payload: { duration_ms: number };
}

export interface StageFailedEvent extends BaseEvent {
  event_type: "stage_failed";
  pipeline_stage: PipelineStage;
  payload: { duration_ms: number; error_type: string; error_message: string };
}

export interface PipelineCompletedEvent extends BaseEvent {
  event_type: "pipeline_completed";
  payload: {
    status: PipelineStatus;
    error: string | null;
    business_answer: BusinessAnswer | null;
  };
}

export interface PipelineFailedEvent extends BaseEvent {
  event_type: "pipeline_failed";
  payload: { error_type: string; error_message: string };
}

export interface HeartbeatEvent extends BaseEvent {
  event_type: "heartbeat";
  payload: { elapsed_ms: number };
}

export interface ClientDisconnectedEvent extends BaseEvent {
  event_type: "client_disconnected";
  payload: Record<string, never>;
}

export type PipelineEvent =
  | PipelineStartedEvent
  | StageStartedEvent
  | StageCompletedEvent
  | StageFailedEvent
  | PipelineCompletedEvent
  | PipelineFailedEvent
  | HeartbeatEvent
  | ClientDisconnectedEvent;

/** The two event types that end a stream -- see `stream_pipeline_events` on the backend. */
export function isTerminalEvent(
  event: PipelineEvent,
): event is PipelineCompletedEvent | PipelineFailedEvent {
  return event.event_type === "pipeline_completed" || event.event_type === "pipeline_failed";
}

export type StreamingTransport = "sse" | "websocket";
