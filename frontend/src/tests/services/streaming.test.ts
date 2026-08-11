/** Phase 22D-7: covers the token-attachment behavior `services/streaming.ts` was missing --
 * `streamQuerySse`/`streamQueryWebSocket` predate Phase 22C authentication and, until this
 * phase, never attached any credential at all (see that module's own docstring for the full
 * story). Mirrors `tests/services/apiAuth.test.ts`'s style for the SSE half (a real `fetch`
 * intercepted by MSW); the WebSocket half uses a small stub class (`StubWebSocket`, the same
 * kind of test double `FakeAuthenticationService`/`ResizeObserverStub` already establish
 * elsewhere in this codebase) since jsdom's real `WebSocket` would attempt an actual network
 * connection with nothing listening on the other end.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { streamQuerySse, streamQueryWebSocket } from "@/services/streaming";
import type { StreamHandlers } from "@/services/streaming";
import { useAuthStore } from "@/store/authStore";
import { server } from "@/tests/mocks/server";
import { pipelineCompletedEventFixture, stageStartedEventFixture } from "@/tests/mocks/fixtures";

const INITIAL_STATE = {
  status: "idle" as const,
  accessToken: null,
  refreshToken: null,
  user: null,
  error: null,
};

beforeEach(() => {
  useAuthStore.setState(INITIAL_STATE);
});

function sseFrame(id: string, event: { event_type: string }): string {
  return `id: ${id}\nevent: ${event.event_type}\ndata: ${JSON.stringify(event)}\n\n`;
}

function streamedResponse(frames: string[], init?: { status?: number }): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder();
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return new HttpResponse(body, { status: init?.status ?? 200 });
}

function collect(): { handlers: StreamHandlers; events: unknown[]; errors: Error[]; done: number } {
  const events: unknown[] = [];
  const errors: Error[] = [];
  const state = { handlers: null as unknown as StreamHandlers, events, errors, done: 0 };
  state.handlers = {
    onEvent: (event) => events.push(event),
    onError: (error) => errors.push(error),
    onDone: () => {
      state.done += 1;
    },
  };
  return state;
}

describe("streamQuerySse", () => {
  it("attaches 'Bearer <accessToken>' when authenticated", async () => {
    useAuthStore.setState({ accessToken: "test-access-token" });
    let receivedAuth: string | null = "unset";
    server.use(
      http.post("/api/v1/query/stream", ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return streamedResponse([]);
      }),
    );

    const { handlers } = collect();
    await new Promise<void>((resolve) => {
      streamQuerySse("q", { ...handlers, onDone: resolve });
    });

    expect(receivedAuth).toBe("Bearer test-access-token");
  });

  it("sends no Authorization header, and no fake credential, when unauthenticated", async () => {
    let receivedAuth: string | null = "unset";
    server.use(
      http.post("/api/v1/query/stream", ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return streamedResponse([]);
      }),
    );

    const { handlers } = collect();
    await new Promise<void>((resolve) => {
      streamQuerySse("q", { ...handlers, onDone: resolve });
    });

    expect(receivedAuth).toBeNull();
  });

  it("never sends the refresh token, even when only a refresh token is present", async () => {
    useAuthStore.setState({ accessToken: null, refreshToken: "mock-refresh-token" });
    let receivedAuth: string | null = "unset";
    let sawRefreshTokenAnywhere = false;
    server.use(
      http.post("/api/v1/query/stream", ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        sawRefreshTokenAnywhere = request.headers.get("Authorization")?.includes("mock-refresh-token") ?? false;
        return streamedResponse([]);
      }),
    );

    const { handlers } = collect();
    await new Promise<void>((resolve) => {
      streamQuerySse("q", { ...handlers, onDone: resolve });
    });

    expect(receivedAuth).toBeNull();
    expect(sawRefreshTokenAnywhere).toBe(false);
  });

  it("still parses SSE frames into events, in order, once authenticated", async () => {
    useAuthStore.setState({ accessToken: "test-access-token" });
    server.use(
      http.post("/api/v1/query/stream", () =>
        streamedResponse([
          sseFrame("evt-1", stageStartedEventFixture),
          sseFrame("evt-9", pipelineCompletedEventFixture),
        ]),
      ),
    );

    const { handlers, events } = collect();
    await new Promise<void>((resolve) => {
      streamQuerySse("q", { ...handlers, onDone: resolve });
    });

    expect(events).toEqual([stageStartedEventFixture, pipelineCompletedEventFixture]);
  });

  it("still surfaces a non-ok response (e.g. a 401 for a missing/expired token) via onError", async () => {
    server.use(http.post("/api/v1/query/stream", () => streamedResponse([], { status: 401 })));

    const { handlers, events, errors } = collect();
    await new Promise<void>((resolve) => {
      streamQuerySse("q", { ...handlers, onDone: resolve });
    });

    expect(events).toEqual([]);
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toContain("401");
  });
});

class StubWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly url: string;
  readyState = StubWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  sentMessages: string[] = [];
  closed = false;

  constructor(url: string) {
    this.url = url;
    StubWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sentMessages.push(data);
  }

  close(): void {
    this.closed = true;
    this.readyState = StubWebSocket.CLOSED;
    this.onclose?.();
  }

  static instances: StubWebSocket[] = [];
}

describe("streamQueryWebSocket", () => {
  beforeEach(() => {
    StubWebSocket.instances = [];
    vi.stubGlobal("WebSocket", StubWebSocket);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("appends '?token=<accessToken>' to the connection URL when authenticated", () => {
    useAuthStore.setState({ accessToken: "test-access-token" });

    streamQueryWebSocket("q", collect().handlers);

    const socket = StubWebSocket.instances[0];
    expect(socket?.url).toContain("?token=test-access-token");
  });

  it("uses the current access token, not a stale or different value", () => {
    useAuthStore.setState({ accessToken: "the-current-token" });

    streamQueryWebSocket("q", collect().handlers);

    expect(StubWebSocket.instances[0]?.url).toContain("token=the-current-token");
  });

  it("never places the refresh token in the URL, even when only a refresh token is present", () => {
    useAuthStore.setState({ accessToken: null, refreshToken: "mock-refresh-token" });

    streamQueryWebSocket("q", collect().handlers);

    const socket = StubWebSocket.instances[0];
    expect(socket?.url).not.toContain("mock-refresh-token");
    expect(socket?.url).not.toContain("token=");
  });

  it("connects with no token parameter at all when unauthenticated (never a fake credential)", () => {
    streamQueryWebSocket("q", collect().handlers);

    expect(StubWebSocket.instances[0]?.url).not.toContain("token=");
  });

  it("still sends the question on open and forwards messages as events", () => {
    useAuthStore.setState({ accessToken: "test-access-token" });
    const { handlers, events } = collect();

    streamQueryWebSocket("a real question", handlers);
    const socket = StubWebSocket.instances[0];
    socket?.onopen?.();
    socket?.onmessage?.({ data: JSON.stringify(stageStartedEventFixture) } as MessageEvent<string>);

    expect(socket?.sentMessages).toEqual([JSON.stringify({ question: "a real question" })]);
    expect(events).toEqual([stageStartedEventFixture]);
  });

  it("still surfaces a connection failure via onError (e.g. the backend rejecting a bad/missing token)", () => {
    const { handlers, errors } = collect();

    streamQueryWebSocket("q", handlers);
    StubWebSocket.instances[0]?.onerror?.();

    expect(errors).toHaveLength(1);
  });

  it("still closes the socket when the returned stop handle is called", () => {
    useAuthStore.setState({ accessToken: "test-access-token" });
    const stop = streamQueryWebSocket("q", collect().handlers);
    const socket = StubWebSocket.instances[0];
    if (socket) socket.readyState = StubWebSocket.OPEN;

    stop();

    expect(socket?.closed).toBe(true);
  });
});