/**
 * Thin REST client over the existing FastAPI service layer (Phase 16). One function per
 * endpoint, each doing exactly three things: serialize the request, call `fetch`, and parse the
 * response into the matching backend DTO -- no business logic, no orchestration, no client-side
 * SQL generation/validation/repair/execution. Every shape here is one of `src/models`' types,
 * reused as-is; this file never re-derives or duplicates what the backend already computed.
 */

import type {
  BusinessAnswer,
  DiagnosticsReport,
  ErrorResponse,
  ExecuteRequest,
  GeneratedSqlResult,
  HealthReport,
  LivenessResponse,
  MetricsSnapshot,
  QuestionRequest,
  QueryMindResponse,
  RepairRequest,
  SettingsResponse,
  SqlInputRequest,
  SQLExecutionResult,
  SQLRepairResult,
  SQLValidationResult,
} from "@/models";
import { ApiError, NetworkError } from "@/models";

/** `/api/v1` by default; overridable for a non-same-origin deployment via `VITE_API_BASE_URL`. */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (cause) {
    throw new NetworkError(
      cause instanceof Error ? cause.message : "The request could not be sent.",
    );
  }

  if (!response.ok) {
    let body: ErrorResponse;
    try {
      body = (await response.json()) as ErrorResponse;
    } catch {
      throw new NetworkError(`Request failed with status ${response.status}.`);
    }
    throw new ApiError(response.status, body);
  }

  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

// -- Query family -----------------------------------------------------------------------------

export function askQuestion(question: string): Promise<QueryMindResponse> {
  return postJson<QueryMindResponse>("/query", { question } satisfies QuestionRequest);
}

export function generateSql(question: string): Promise<GeneratedSqlResult> {
  return postJson<GeneratedSqlResult>("/query/sql", { question } satisfies QuestionRequest);
}

export function validateSql(
  sql: string,
  dialect?: SqlInputRequest["dialect"],
): Promise<SQLValidationResult> {
  const body: SqlInputRequest = dialect === undefined ? { sql } : { sql, dialect };
  return postJson<SQLValidationResult>("/query/validate", body);
}

export function repairSql(
  question: string,
  validationResult: SQLValidationResult,
): Promise<SQLRepairResult> {
  return postJson<SQLRepairResult>("/query/repair", {
    question,
    validation_result: validationResult,
  } satisfies RepairRequest);
}

export function executeSql(validationResult: SQLValidationResult): Promise<SQLExecutionResult> {
  return postJson<SQLExecutionResult>("/query/execute", {
    validation_result: validationResult,
  } satisfies ExecuteRequest);
}

export function formatResult(executionResult: SQLExecutionResult): Promise<BusinessAnswer> {
  return postJson<BusinessAnswer>("/query/format", executionResult);
}

// -- Health / diagnostics / metrics ------------------------------------------------------------

export function getHealth(): Promise<HealthReport> {
  return request<HealthReport>("/health");
}

export function getLiveness(): Promise<LivenessResponse> {
  return request<LivenessResponse>("/health/live");
}

export function getDiagnostics(): Promise<DiagnosticsReport> {
  return request<DiagnosticsReport>("/health/diagnostics");
}

export function getMetrics(): Promise<MetricsSnapshot> {
  return request<MetricsSnapshot>("/health/metrics");
}

// -- Settings -----------------------------------------------------------------------------------

export function getSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>("/settings");
}
