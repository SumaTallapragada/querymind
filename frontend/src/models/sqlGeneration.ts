/** Mirrors `querymind.sql_generation.models`. */

import type { GenerationMetrics } from "./llm";

export type SQLDialect = "postgresql" | "mysql" | "sqlite" | "bigquery" | "snowflake";

export type ExtractionMethod = "fenced_sql_block" | "fenced_generic_block" | "raw_text";

export type SQLStatementType = "select" | "with" | "insert" | "update" | "delete" | "unknown";

export interface SQLGenerationStatistics {
  extraction_method: ExtractionMethod;
  raw_sql_length: number;
  normalized_sql_length: number;
  normalization_changed_sql: boolean;
  generation_latency_ms: number;
}

export interface GeneratedSQL {
  sql: string;
  statement_type: SQLStatementType;
  raw_llm_content: string;
  dialect: SQLDialect;
  llm_metrics: GenerationMetrics;
  statistics: SQLGenerationStatistics;
}
