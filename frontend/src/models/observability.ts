/** Mirrors `querymind.observability.models` -- health, diagnostics, and metrics. */

export type HealthStatus = "healthy" | "unhealthy" | "unknown";

export interface HealthCheck {
  name: string;
  status: HealthStatus;
  message: string | null;
}

export interface HealthReport {
  checks: HealthCheck[];
  overall_status: HealthStatus;
  generated_at: string;
}

export interface LivenessResponse {
  status: "ok";
}

export type DiagnosticStatus = "pass" | "warning" | "error";

export interface DiagnosticFinding {
  check_name: string;
  status: DiagnosticStatus;
  message: string;
  details: string | null;
}

export interface DiagnosticsReport {
  findings: DiagnosticFinding[];
  overall_status: DiagnosticStatus;
  generated_at: string;
}

export interface StageMetric {
  stage: string;
  call_count: number;
  total_latency_ms: number;
  average_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
}

export interface MetricsSnapshot {
  captured_at: string;
  pipeline_run_count: number;
  pipeline_success_count: number;
  pipeline_failure_count: number;
  average_pipeline_latency_ms: number;
  stage_metrics: StageMetric[];
  validation_failure_count: number;
  repair_attempted_count: number;
  repair_success_count: number;
  repair_success_rate: number;
  sql_execution_count: number;
  total_rows_returned: number;
  llm_prompt_tokens: number;
  llm_completion_tokens: number;
  cache_hit_count: number;
  cache_miss_count: number;
  startup_time_ms: number | null;
}
