/** Mirrors `querymind.api.models.request` -- every request body this frontend ever sends. */

import type { SQLDialect } from "./sqlGeneration";
import type { SQLValidationResult } from "./sqlValidation";

export interface QuestionRequest {
  question: string;
}

export interface SqlInputRequest {
  sql: string;
  dialect?: SQLDialect;
}

export interface RepairRequest {
  question: string;
  validation_result: SQLValidationResult;
}

export interface ExecuteRequest {
  validation_result: SQLValidationResult;
}
