/**
 * Streaming client over the existing Phase 17 endpoints (`POST /query/stream` for SSE,
 * `/ws/query` for WebSocket). The backend determines what each transport looks like on the
 * wire; this module's only job is turning that wire format back into `PipelineEvent`s and
 * handing them to a caller-supplied callback -- it never inspects, alters, or reorders what the
 * backend sent.
 *
 * The browser's built-in `EventSource` cannot be used for SSE here: it only ever issues plain
 * `GET` requests with no body, but `POST /query/stream` needs a JSON `{"question": ...}` body.
 * `streamQuerySse` instead reads the `fetch` response body as a stream and parses the same
 * `event:`/`data:` framing `querymind.streaming.sse._format_sse_frame` writes.
 *
 * Authentication (Phase 22D-7): both `POST /query/stream` and `/ws/query` require at least the
 * `analyst` role (`querymind.streaming.sse`/`.websocket`'s own docstrings) -- this module reads
 * the current *access* token directly from `useAuthStore.getState()`, the exact same source
 * `services/api.ts`'s `request()` already uses, rather than duplicating token storage or adding
 * a second auth store. Only the access token is ever sent here; the refresh token never leaves
 * `authStore`/`services/api.ts`'s own refresh call. SSE attaches it the ordinary way
 * (`Authorization: Bearer <token>` header, since `fetch` can set arbitrary headers); a browser's
 * native `WebSocket` constructor cannot set custom headers at all, so `/ws/query` -- which
 * already accepts a `?token=` query parameter for exactly this reason, see
 * `querymind.streaming.websocket._authenticate_and_authorize`'s own docstring -- gets the token
 * appended to its URL instead. Neither transport attempts an automatic refresh-and-retry on
 * authentication failure the way `services/api.ts` does for ordinary requests: `api.ts`'s dance
 * retries one already-complete request/response cycle, but a rejected SSE call fails before any
 * stream begins and a rejected WebSocket handshake closes before `.accept()`, so "retry" here
 * would mean re-issuing the whole call with a freshly refreshed token -- a real behavior change,
 * not the smallest correct fix for a frontend that predates Phase 22C authentication entirely.
 * Both failure cases already surface safely today (via this module's own `onError`/`throw`
 * handling below), just now for the *legitimate* reason of a missing/expired token instead of
 * unconditionally. If in-flight token refresh for an open streaming connection is ever needed,
 * it belongs in a dedicated follow-up, not folded into this fix.
 */

import type { PipelineEvent } from "@/models";
import { isTerminalEvent } from "@/models";
import { useAuthStore } from "@/store/authStore";
import { API_BASE_URL } from "./api";

export interface StreamHandlers {
  onEvent: (event: PipelineEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
}

/** Stop a stream started by `streamQuerySse`/`streamQueryWebSocket`. Idempotent. */
export type StreamHandle = () => void;

function parseSseFrame(frame: string): PipelineEvent | null {
  const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
  if (!dataLine) return null;
  try {
    return JSON.parse(dataLine.slice("data: ".length)) as PipelineEvent;
  } catch {
    return null;
  }
}

export function streamQuerySse(question: string, handlers: StreamHandlers): StreamHandle {
  const controller = new AbortController();
  let done = false;
  const finish = (): void => {
    if (done) return;
    done = true;
    handlers.onDone?.();
  };

  void (async () => {
    try {
      const accessToken = useAuthStore.getState().accessToken;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      const response = await fetch(`${API_BASE_URL}/query/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ question }),
        signal: controller.signal,
      });
      if (!response.ok || response.body === null) {
        throw new Error(`Stream request failed with status ${response.status}.`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const event = parseSseFrame(frame);
          if (event !== null) handlers.onEvent(event);
        }
      }
      finish();
    } catch (error) {
      if (controller.signal.aborted) return; // intentional cancellation, not a failure
      handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
      finish();
    }
  })();

  return () => controller.abort();
}

function buildWebSocketUrl(path: string): string {
  const override = import.meta.env.VITE_WS_BASE_URL as string | undefined;
  // The browser's native `WebSocket` constructor cannot set an `Authorization` header (or any
  // custom header) -- `?token=` is the existing, already-implemented fallback
  // `querymind.streaming.websocket._authenticate_and_authorize` accepts for exactly this reason.
  // Never the refresh token: only the short-lived access token is ever placed in a URL.
  const accessToken = useAuthStore.getState().accessToken;
  const query = accessToken ? `?token=${encodeURIComponent(accessToken)}` : "";
  if (override !== undefined) return `${override}${path}${query}`;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}${query}`;
}

export function streamQueryWebSocket(question: string, handlers: StreamHandlers): StreamHandle {
  const socket = new WebSocket(buildWebSocketUrl("/ws/query"));
  let done = false;
  const finish = (): void => {
    if (done) return;
    done = true;
    handlers.onDone?.();
  };

  socket.onopen = () => socket.send(JSON.stringify({ question }));

  socket.onmessage = (messageEvent: MessageEvent<string>) => {
    let event: PipelineEvent;
    try {
      event = JSON.parse(messageEvent.data) as PipelineEvent;
    } catch {
      return; // an unparseable frame is dropped, never surfaced as a fatal error
    }
    handlers.onEvent(event);
    if (isTerminalEvent(event)) finish();
  };

  socket.onerror = () => {
    handlers.onError?.(new Error("The WebSocket connection failed."));
  };

  socket.onclose = () => finish();

  return () => {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
  };
}

export function streamQuery(
  transport: "sse" | "websocket",
  question: string,
  handlers: StreamHandlers,
): StreamHandle {
  return transport === "sse"
    ? streamQuerySse(question, handlers)
    : streamQueryWebSocket(question, handlers);
}
