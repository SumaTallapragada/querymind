/** Mirrors `querymind.api.models.response.ErrorResponse` -- the body of every mapped-exception
 * error response the backend returns. Never a raw traceback.
 */

export interface ErrorResponse {
  detail: string;
  error_type: string;
}

/** Thrown by `services/api.ts` for any non-2xx response, carrying the parsed `ErrorResponse`
 * when the backend returned one (always does, for a mapped exception).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly errorType: string;

  constructor(status: number, body: ErrorResponse) {
    super(body.detail);
    this.name = "ApiError";
    this.status = status;
    this.errorType = body.error_type;
  }
}

/** Thrown when a response can't be parsed as `ErrorResponse` at all (a transport-level
 * failure, a proxy error page, etc.) -- kept distinct from `ApiError` so the UI can still show
 * *something* useful without pretending it understood a structured backend error.
 */
export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}
