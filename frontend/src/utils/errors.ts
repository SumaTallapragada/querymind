import { ApiError, NetworkError } from "@/models";

/** A safe, human-readable message for any error this app can throw -- never a stack trace
 * (rule 9 of the Phase 18 spec).
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof NetworkError) return error.message;
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred.";
}
