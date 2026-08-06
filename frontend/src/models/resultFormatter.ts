/** Mirrors `querymind.result_formatter.models`. */

import type { QueryColumn, QueryValue, SQLExecutionResult } from "./sqlExecution";

export type AnswerType = "scalar" | "table" | "empty_result" | "aggregation" | "detail";

export interface AnswerSummary {
  title: string;
  description: string;
  row_count: number;
  column_count: number;
  contains_numeric: boolean;
  contains_dates: boolean;
}

export interface FormattedValue {
  original_value: QueryValue;
  formatted_value: string;
  detected_type: string;
}

export interface FormattedRow {
  values: FormattedValue[];
}

export interface FormattedTable {
  columns: QueryColumn[];
  rows: FormattedRow[];
}

export interface AnswerStatistics {
  formatting_latency_ms: number;
  rows_processed: number;
  columns_processed: number;
  values_formatted: number;
}

export interface BusinessAnswer {
  answer_type: AnswerType;
  summary: AnswerSummary;
  formatted_table: FormattedTable;
  statistics: AnswerStatistics;
  execution_result: SQLExecutionResult;
}
