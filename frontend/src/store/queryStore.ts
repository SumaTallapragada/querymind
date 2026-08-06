/**
 * Client-side session state for "ask a question" -- both the direct `POST /query` request and
 * a live SSE/WebSocket stream. This is genuinely UI state, not server data TanStack Query
 * should own: a stream is a sequence of events arriving over time, not one cacheable
 * request/response pair. `hooks/useQuery.ts`/`useStreaming.ts` are the only callers that
 * mutate this store; components only ever read from it.
 */

import { create } from "zustand";
import type { PipelineEvent, QueryMindResponse } from "@/models";

export type QueryMode = "direct" | "streaming";

/**
 * The *session's* lifecycle -- distinct from `response.status` ("success"/"failed"), which is
 * the *pipeline's* outcome. `"settled"` covers both a successful and a pipeline-level-failed
 * response (either way, a well-formed `QueryMindResponse` came back); `"transport_error"` is
 * reserved for when nothing did -- a dropped connection, a network failure, no response at all.
 */
export type QuerySessionStatus = "idle" | "running" | "settled" | "transport_error";

export interface QueryHistoryEntry {
  id: string;
  question: string;
  askedAt: string;
  mode: QueryMode;
  status: "success" | "failed";
  totalLatencyMs: number | null;
}

interface QueryState {
  question: string;
  mode: QueryMode;
  status: QuerySessionStatus;
  events: PipelineEvent[];
  response: QueryMindResponse | null;
  errorMessage: string | null;
  history: QueryHistoryEntry[];

  setQuestion: (question: string) => void;
  setMode: (mode: QueryMode) => void;
  beginQuery: (question: string) => void;
  appendEvent: (event: PipelineEvent) => void;
  succeed: (response: QueryMindResponse) => void;
  fail: (message: string) => void;
  clearHistory: () => void;
  reset: () => void;
}

const MAX_HISTORY_ENTRIES = 50;

function historyId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useQueryStore = create<QueryState>()((set, get) => ({
  question: "",
  mode: "direct",
  status: "idle",
  events: [],
  response: null,
  errorMessage: null,
  history: [],

  setQuestion: (question) => set({ question }),
  setMode: (mode) => set({ mode }),

  beginQuery: (question) =>
    set({
      question,
      status: "running",
      events: [],
      response: null,
      errorMessage: null,
    }),

  appendEvent: (event) => set((state) => ({ events: [...state.events, event] })),

  succeed: (response) => {
    const entry: QueryHistoryEntry = {
      id: historyId(),
      question: get().question,
      askedAt: new Date().toISOString(),
      mode: get().mode,
      status: response.status,
      totalLatencyMs: response.statistics.total_latency_ms,
    };
    set((state) => ({
      status: "settled",
      response,
      history: [entry, ...state.history].slice(0, MAX_HISTORY_ENTRIES),
    }));
  },

  fail: (message) => {
    const entry: QueryHistoryEntry = {
      id: historyId(),
      question: get().question,
      askedAt: new Date().toISOString(),
      mode: get().mode,
      status: "failed",
      totalLatencyMs: null,
    };
    set((state) => ({
      status: "transport_error",
      errorMessage: message,
      history: [entry, ...state.history].slice(0, MAX_HISTORY_ENTRIES),
    }));
  },

  clearHistory: () => set({ history: [] }),

  reset: () =>
    set({
      status: "idle",
      events: [],
      response: null,
      errorMessage: null,
    }),
}));
