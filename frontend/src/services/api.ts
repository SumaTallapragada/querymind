/**
 * Thin REST client over the existing FastAPI service layer (Phase 16). One function per
 * endpoint, each doing exactly three things: serialize the request, call `fetch`, and parse the
 * response into the matching backend DTO -- no business logic, no orchestration, no client-side
 * SQL generation/validation/repair/execution. Every shape here is one of `src/models`' types,
 * reused as-is; this file never re-derives or duplicates what the backend already computed.
 *
 * Authentication (Phase 22C) lives here too, not in a parallel client: `request()` attaches the
 * current access token to every call (except the `/auth/login`/`/auth/refresh` calls that don't
 * have one yet) and, on a `401`, refreshes once and retries -- the one place that dance happens,
 * so no page/hook re-implements it. Token storage itself belongs to `store/authStore.ts`; this
 * file only reads/writes it via `useAuthStore.getState()`, never rendering or logging a token.
 */

import type {
  BusinessAnswer,
  DiagnosticsReport,
  ErrorResponse,
  ExecuteRequest,
  GeneratedSqlResult,
  HealthReport,
  LivenessResponse,
  LoginRequest,
  MetricsSnapshot,
  QuestionRequest,
  QueryMindResponse,
  RefreshRequest,
  RepairRequest,
  SettingsResponse,
  SqlInputRequest,
  SQLExecutionResult,
  SQLRepairResult,
  SQLValidationResult,
  TokenPair,
  UserRead,
} from "@/models";
import { ApiError, NetworkError } from "@/models";
import { useAuthStore } from "@/store/authStore";

/** `/api/v1` by default; overridable for a non-same-origin deployment via `VITE_API_BASE_URL`. */
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

/** No access token exists yet when calling these -- never attach an `Authorization` header. */
const NO_AUTH_HEADER_PATHS = new Set<string>(["/auth/login", "/auth/refresh"]);

/** Never worth a refresh-and-retry: a 401 here IS the auth attempt, not a side effect of one. */
const NO_REFRESH_RETRY_PATHS = new Set<string>(["/auth/login", "/auth/refresh", "/auth/logout"]);

/** Shared by every concurrent 401 so only one `/auth/refresh` call is ever in flight at once. */
let refreshPromise: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const currentRefreshToken = useAuthStore.getState().refreshToken;
  if (!currentRefreshToken) return null;
  try {
    const tokens = await refreshTokenPair(currentRefreshToken);
    useAuthStore.getState().setTokens(tokens);
    return tokens.access_token;
  } catch {
    useAuthStore.getState().clear();
    return null;
  }
}

function getRefreshedAccessToken(): Promise<string | null> {
  refreshPromise ??= performRefresh().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

interface RequestOptions {
  /** Skip JSON body parsing for endpoints that return no content (e.g. `204` on logout). */
  parseJson?: boolean;
}

async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(init?.headers as Record<string, string> | undefined),
    };
    const accessToken = useAuthStore.getState().accessToken;
    if (accessToken && !NO_AUTH_HEADER_PATHS.has(path)) {
      headers.Authorization = `Bearer ${accessToken}`;
    }
    try {
      return await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
    } catch (cause) {
      throw new NetworkError(
        cause instanceof Error ? cause.message : "The request could not be sent.",
      );
    }
  };

  let response = await doFetch();

  if (response.status === 401 && !NO_REFRESH_RETRY_PATHS.has(path)) {
    const refreshedToken = await getRefreshedAccessToken();
    if (refreshedToken) {
      response = await doFetch();
    }
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

  if (options?.parseJson === false) return undefined as T;
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

// -- Auth ---------------------------------------------------------------------------------------

export function login(username: string, password: string): Promise<TokenPair> {
  return postJson<TokenPair>("/auth/login", { username, password } satisfies LoginRequest);
}

export function refreshTokenPair(refreshToken: string): Promise<TokenPair> {
  return postJson<TokenPair>("/auth/refresh", {
    refresh_token: refreshToken,
  } satisfies RefreshRequest);
}

export async function logoutRequest(refreshToken: string): Promise<void> {
  await request<void>(
    "/auth/logout",
    { method: "POST", body: JSON.stringify({ refresh_token: refreshToken } satisfies RefreshRequest) },
    { parseJson: false },
  );
}

export function getCurrentUser(): Promise<UserRead> {
  return request<UserRead>("/auth/me");
}
