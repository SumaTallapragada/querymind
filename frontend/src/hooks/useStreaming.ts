/** Drives a live SSE/WebSocket stream (`services/streaming.ts`) into `queryStore`. The backend
 * decides what transport looks like on the wire (rule 4 of the Phase 18 spec); this hook only
 * starts/stops the connection and forwards whatever it receives.
 */

import { useCallback, useEffect, useRef } from "react";
import { streamQuery, type StreamHandle } from "@/services/streaming";
import { useQueryStore } from "@/store/queryStore";
import { useUiStore } from "@/store/uiStore";
import { errorMessage } from "@/utils/errors";
import { buildResponseFromCompletedEvent, buildResponseFromFailedEvent } from "@/utils/streamingDerivation";

export interface UseStreamingResult {
  start: (question: string) => void;
  /** User-initiated cancellation: closes the connection and returns the session to idle. */
  stop: () => void;
}

export function useStreaming(): UseStreamingResult {
  const handleRef = useRef<StreamHandle | null>(null);
  const transport = useUiStore((state) => state.streamingTransport);
  const beginQuery = useQueryStore((state) => state.beginQuery);
  const setMode = useQueryStore((state) => state.setMode);
  const appendEvent = useQueryStore((state) => state.appendEvent);
  const succeed = useQueryStore((state) => state.succeed);
  const fail = useQueryStore((state) => state.fail);
  const reset = useQueryStore((state) => state.reset);

  const closeConnection = useCallback(() => {
    handleRef.current?.();
    handleRef.current = null;
  }, []);

  const start = useCallback(
    (question: string) => {
      closeConnection();
      setMode("streaming");
      beginQuery(question);

      handleRef.current = streamQuery(transport, question, {
        onEvent: (event) => {
          appendEvent(event);
          if (event.event_type === "pipeline_completed") {
            const events = useQueryStore.getState().events;
            succeed(buildResponseFromCompletedEvent(question, events, event));
          } else if (event.event_type === "pipeline_failed") {
            const events = useQueryStore.getState().events;
            succeed(buildResponseFromFailedEvent(question, events, event));
          }
        },
        onError: (error) => fail(errorMessage(error)),
      });
    },
    [transport, closeConnection, setMode, beginQuery, appendEvent, succeed, fail],
  );

  const stop = useCallback(() => {
    closeConnection();
    if (useQueryStore.getState().status === "running") reset();
  }, [closeConnection, reset]);

  useEffect(() => closeConnection, [closeConnection]);

  return { start, stop };
}
