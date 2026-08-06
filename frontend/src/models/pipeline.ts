/** Mirrors `querymind.orchestrator.models`. */

import type { BusinessAnswer } from "./resultFormatter";
import type { GeneratedSQL } from "./sqlGeneration";
import type { SQLExecutionResult } from "./sqlExecution";
import type { SQLRepairResult } from "./sqlRepair";
import type { SQLValidationResult } from "./sqlValidation";

/** Every independently timed stage of the end-to-end pipeline, in execution order. */
export const PIPELINE_STAGES = [
  "nlu",
  "schema_linking",
  "business_knowledge",
  "retrieval",
  "prompt_compilation",
  "sql_generation",
  "llm",
  "sql_validation",
  "sql_repair",
  "sql_execution",
  "result_formatting",
] as const;

export type PipelineStage = (typeof PIPELINE_STAGES)[number];

/** Human-readable labels for the pipeline timeline UI. */
export const PIPELINE_STAGE_LABELS: Record<PipelineStage, string> = {
  nlu: "NLU",
  schema_linking: "Schema Linking",
  business_knowledge: "Business Knowledge",
  retrieval: "Retrieval",
  prompt_compilation: "Prompt Compilation",
  sql_generation: "SQL Generation",
  llm: "LLM",
  sql_validation: "Validation",
  sql_repair: "Repair",
  sql_execution: "Execution",
  result_formatting: "Formatting",
};

export interface StageTiming {
  stage: PipelineStage;
  latency_ms: number;
}

export interface PipelineStatistics {
  total_latency_ms: number;
  stage_timings: StageTiming[];
  repair_attempted: boolean;
  repair_performed: boolean;
}

export type PipelineStatus = "success" | "failed";

export interface QueryMindResponse {
  original_question: string;
  business_answer: BusinessAnswer | null;
  generated_sql: GeneratedSQL | null;
  validation_result: SQLValidationResult | null;
  repair_result: SQLRepairResult | null;
  execution_result: SQLExecutionResult | null;
  statistics: PipelineStatistics;
  status: PipelineStatus;
  error: string | null;
}

export interface GeneratedSqlResult {
  original_question: string;
  generated_sql: GeneratedSQL;
  validation_result: SQLValidationResult;
  repair_result: SQLRepairResult | null;
  statistics: PipelineStatistics;
}
