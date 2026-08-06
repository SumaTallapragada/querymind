/** Mirrors `querymind.sql_execution.models`. */

import type { SQLDialect } from "./sqlGeneration";

export type ExecutionStatus = "success" | "failed" | "rejected" | "timeout";

export interface ExecutionError {
  code: string;
  message: string;
  details: string | null;
}

export interface QueryColumn {
  name: string;
  database_type: string;
  python_type: string;
  nullable: boolean | null;
}

/** A database row's values -- genuinely heterogeneous, matching `QueryRow.values: tuple[Any, ...]`. */
export type QueryValue = string | number | boolean | null;

export interface QueryRow {
  values: QueryValue[];
}

export interface QueryResult {
  columns: QueryColumn[];
  rows: QueryRow[];
  row_count: number;
}

export interface ExecutionStatistics {
  execution_latency_ms: number;
  rows_returned: number;
  columns_returned: number;
  database_name: string;
  dialect: SQLDialect;
}

export interface SQLExecutionResult {
  status: ExecutionStatus;
  executed_sql: string;
  query_result: QueryResult | null;
  statistics: ExecutionStatistics;
  execution_error: ExecutionError | null;
}
