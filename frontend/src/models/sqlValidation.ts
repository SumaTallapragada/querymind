/** Mirrors `querymind.sql_validation.models`. */

import type { GeneratedSQL } from "./sqlGeneration";

export type ValidationSeverity = "error" | "warning";

export interface ValidationIssue {
  code: string;
  severity: ValidationSeverity;
  message: string;
  location: string | null;
  related_object: string | null;
}

export interface ValidatorExecutionTime {
  validator: string;
  duration_ms: number;
}

export interface ValidationStatistics {
  validation_latency_ms: number;
  validator_execution_times: ValidatorExecutionTime[];
  table_count: number;
  column_count: number;
  join_count: number;
  function_count: number;
  error_count: number;
  warning_count: number;
}

export interface SQLValidationResult {
  generated_sql: GeneratedSQL;
  is_valid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  validated_tables: string[];
  validated_columns: string[];
  validated_functions: string[];
  validation_statistics: ValidationStatistics;
}
