/** Mirrors `querymind.sql_repair.models`. */

import type { GenerationMetrics } from "./llm";
import type { GeneratedSQL } from "./sqlGeneration";
import type { SQLValidationResult } from "./sqlValidation";

export type RepairReason =
  | "unknown_table"
  | "unknown_column"
  | "schema_issue"
  | "invalid_join"
  | "missing_group_by"
  | "aggregate_error"
  | "alias_issue"
  | "unsupported_function"
  | "dialect_issue"
  | "business_rule_mismatch"
  | "unsupported_statement"
  | "syntax_error"
  | "other";

export type RepairStatus = "repaired" | "max_attempts_reached" | "no_progress" | "unrepairable";

export interface RepairAttempt {
  attempt_number: number;
  repair_reason: RepairReason;
  input_sql: string;
  repaired_sql: string;
  validation_result: SQLValidationResult;
  prompt_version: string;
  llm_metrics: GenerationMetrics;
  success: boolean;
}

export interface RepairHistory {
  attempts: RepairAttempt[];
}

export interface RepairStatistics {
  attempt_count: number;
  successful_repairs: number;
  failed_repairs: number;
  repair_latency_ms: number;
  average_validation_latency_ms: number;
}

export interface SQLRepairResult {
  original_sql: GeneratedSQL;
  final_sql: GeneratedSQL;
  final_validation_result: SQLValidationResult;
  history: RepairHistory;
  statistics: RepairStatistics;
  status: RepairStatus;
}
