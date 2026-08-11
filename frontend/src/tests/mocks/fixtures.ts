/** Shared sample data for tests -- one representative instance per backend DTO, reused by both
 * MSW handlers (`handlers.ts`) and any test that needs to build a `QueryMindResponse`/event by
 * hand. Every field is populated; nothing here is partial or `as any`.
 */

import type {
  BusinessAnswer,
  DiagnosticsReport,
  GeneratedSQL,
  HealthReport,
  MetricsSnapshot,
  PipelineCompletedEvent,
  PipelineFailedEvent,
  PipelineStartedEvent,
  QueryMindResponse,
  SettingsResponse,
  SQLExecutionResult,
  SQLRepairResult,
  SQLValidationResult,
  StageCompletedEvent,
  StageFailedEvent,
  StageStartedEvent,
  TokenPair,
  UserRead,
} from "@/models";

export const generatedSqlFixture: GeneratedSQL = {
  sql: "SELECT customer_id, SUM(amount) AS revenue FROM orders GROUP BY customer_id ORDER BY revenue DESC LIMIT 5",
  statement_type: "select",
  raw_llm_content: "```sql\nSELECT customer_id, SUM(amount) AS revenue FROM orders GROUP BY customer_id ORDER BY revenue DESC LIMIT 5\n```",
  dialect: "postgresql",
  llm_metrics: {
    provider: "claude",
    model: "claude-sonnet-5",
    latency_ms: 842,
    token_usage: { prompt_tokens: 512, completion_tokens: 64 },
    retry_count: 0,
    finish_reason: "complete",
  },
  statistics: {
    extraction_method: "fenced_sql_block",
    raw_sql_length: 120,
    normalized_sql_length: 110,
    normalization_changed_sql: true,
    generation_latency_ms: 842,
  },
};

export const sqlValidationResultFixture: SQLValidationResult = {
  generated_sql: generatedSqlFixture,
  is_valid: true,
  errors: [],
  warnings: [
    {
      code: "W_IMPLICIT_CAST",
      severity: "warning",
      message: "Implicit cast from numeric to text in ORDER BY.",
      location: "ORDER BY revenue DESC",
      related_object: "revenue",
    },
  ],
  validated_tables: ["orders"],
  validated_columns: ["customer_id", "amount"],
  validated_functions: ["SUM"],
  validation_statistics: {
    validation_latency_ms: 12.4,
    validator_execution_times: [{ validator: "schema", duration_ms: 4.1 }],
    table_count: 1,
    column_count: 2,
    join_count: 0,
    function_count: 1,
    error_count: 0,
    warning_count: 1,
  },
};

export const invalidValidationResultFixture: SQLValidationResult = {
  ...sqlValidationResultFixture,
  is_valid: false,
  errors: [
    {
      code: "E_UNKNOWN_TABLE",
      severity: "error",
      message: "Table 'custmers' does not exist.",
      location: "FROM custmers",
      related_object: "custmers",
    },
  ],
};

export const sqlRepairResultFixture: SQLRepairResult = {
  original_sql: generatedSqlFixture,
  final_sql: generatedSqlFixture,
  final_validation_result: sqlValidationResultFixture,
  history: {
    attempts: [
      {
        attempt_number: 1,
        repair_reason: "unknown_table",
        input_sql: "SELECT * FROM custmers",
        repaired_sql: generatedSqlFixture.sql,
        validation_result: sqlValidationResultFixture,
        prompt_version: "v3",
        llm_metrics: generatedSqlFixture.llm_metrics,
        success: true,
      },
    ],
  },
  statistics: {
    attempt_count: 1,
    successful_repairs: 1,
    failed_repairs: 0,
    repair_latency_ms: 610,
    average_validation_latency_ms: 12.4,
  },
  status: "repaired",
};

export const sqlExecutionResultFixture: SQLExecutionResult = {
  status: "success",
  executed_sql: generatedSqlFixture.sql,
  query_result: {
    columns: [
      { name: "customer_id", database_type: "integer", python_type: "int", nullable: false },
      { name: "revenue", database_type: "numeric", python_type: "float", nullable: false },
    ],
    rows: [
      { values: [101, 48210.5] },
      { values: [102, 39120.0] },
    ],
    row_count: 2,
  },
  statistics: {
    execution_latency_ms: 34.2,
    rows_returned: 2,
    columns_returned: 2,
    database_name: "querymind",
    dialect: "postgresql",
  },
  execution_error: null,
};

export const failedExecutionResultFixture: SQLExecutionResult = {
  status: "failed",
  executed_sql: generatedSqlFixture.sql,
  query_result: null,
  statistics: {
    execution_latency_ms: 5.1,
    rows_returned: 0,
    columns_returned: 0,
    database_name: "querymind",
    dialect: "postgresql",
  },
  execution_error: {
    code: "E_QUERY_FAILED",
    message: "relation \"orders\" does not exist",
    details: null,
  },
};

export const businessAnswerFixture: BusinessAnswer = {
  answer_type: "table",
  summary: {
    title: "Top 5 customers by revenue",
    description: "Customer 101 leads with $48,210.50 in revenue.",
    row_count: 2,
    column_count: 2,
    contains_numeric: true,
    contains_dates: false,
  },
  formatted_table: {
    columns: sqlExecutionResultFixture.query_result!.columns,
    rows: [
      {
        values: [
          { original_value: 101, formatted_value: "101", detected_type: "integer" },
          { original_value: 48210.5, formatted_value: "$48,210.50", detected_type: "currency" },
        ],
      },
      {
        values: [
          { original_value: 102, formatted_value: "102", detected_type: "integer" },
          { original_value: 39120.0, formatted_value: "$39,120.00", detected_type: "currency" },
        ],
      },
    ],
  },
  statistics: {
    formatting_latency_ms: 3.8,
    rows_processed: 2,
    columns_processed: 2,
    values_formatted: 4,
  },
  execution_result: sqlExecutionResultFixture,
};

export const queryMindResponseFixture: QueryMindResponse = {
  original_question: "Who are our top 5 customers by revenue?",
  business_answer: businessAnswerFixture,
  generated_sql: generatedSqlFixture,
  validation_result: sqlValidationResultFixture,
  repair_result: null,
  execution_result: sqlExecutionResultFixture,
  statistics: {
    total_latency_ms: 1240.5,
    stage_timings: [
      { stage: "nlu", latency_ms: 80 },
      { stage: "schema_linking", latency_ms: 60 },
      { stage: "business_knowledge", latency_ms: 40 },
      { stage: "retrieval", latency_ms: 55 },
      { stage: "prompt_compilation", latency_ms: 15 },
      { stage: "sql_generation", latency_ms: 842 },
      { stage: "llm", latency_ms: 842 },
      { stage: "sql_validation", latency_ms: 12.4 },
      { stage: "sql_execution", latency_ms: 34.2 },
      { stage: "result_formatting", latency_ms: 3.8 },
    ],
    repair_attempted: false,
    repair_performed: false,
  },
  status: "success",
  error: null,
};

export const failedQueryMindResponseFixture: QueryMindResponse = {
  original_question: "asdf",
  business_answer: null,
  generated_sql: null,
  validation_result: null,
  repair_result: null,
  execution_result: null,
  statistics: { total_latency_ms: 12, stage_timings: [], repair_attempted: false, repair_performed: false },
  status: "failed",
  error: "The question could not be understood.",
};

export const healthReportFixture: HealthReport = {
  checks: [
    { name: "database", status: "healthy", message: null },
    { name: "llm_provider", status: "healthy", message: "Reachable in 42ms." },
  ],
  overall_status: "healthy",
  generated_at: "2026-08-06T12:00:00Z",
};

export const unhealthyHealthReportFixture: HealthReport = {
  checks: [
    { name: "database", status: "unhealthy", message: "Connection refused." },
    { name: "llm_provider", status: "healthy", message: null },
  ],
  overall_status: "unhealthy",
  generated_at: "2026-08-06T12:00:00Z",
};

export const diagnosticsReportFixture: DiagnosticsReport = {
  findings: [
    { check_name: "database_connectivity", status: "pass", message: "Connected.", details: null },
    { check_name: "llm_api_key", status: "warning", message: "Using a development key.", details: "env=development" },
  ],
  overall_status: "warning",
  generated_at: "2026-08-06T12:00:00Z",
};

export const metricsSnapshotFixture: MetricsSnapshot = {
  captured_at: "2026-08-06T12:00:00Z",
  pipeline_run_count: 128,
  pipeline_success_count: 120,
  pipeline_failure_count: 8,
  average_pipeline_latency_ms: 980.4,
  stage_metrics: [
    {
      stage: "sql_generation",
      call_count: 128,
      total_latency_ms: 107776,
      average_latency_ms: 842,
      min_latency_ms: 400,
      max_latency_ms: 1500,
    },
    {
      stage: "sql_validation",
      call_count: 128,
      total_latency_ms: 1587,
      average_latency_ms: 12.4,
      min_latency_ms: 5,
      max_latency_ms: 30,
    },
  ],
  validation_failure_count: 6,
  repair_attempted_count: 10,
  repair_success_count: 8,
  repair_success_rate: 0.8,
  sql_execution_count: 122,
  total_rows_returned: 4310,
  llm_prompt_tokens: 65536,
  llm_completion_tokens: 8192,
  cache_hit_count: 40,
  cache_miss_count: 88,
  startup_time_ms: 320,
};

export const settingsResponseFixture: SettingsResponse = {
  app_name: "QueryMind",
  version: "0.18.0",
  environment: "development",
  api_v1_prefix: "/api/v1",
  database_engine: "PostgreSQL",
  database_name: "querymind",
  llm_provider: "claude",
  llm_model: "claude-sonnet-5",
  streaming_transports: ["sse", "websocket"],
};

const baseEvent = {
  event_id: "evt-1",
  correlation_id: "corr-1",
  timestamp: "2026-08-06T12:00:00.000Z",
};

export const pipelineStartedEventFixture: PipelineStartedEvent = {
  ...baseEvent,
  event_id: "evt-0",
  pipeline_stage: null,
  event_type: "pipeline_started",
  payload: { original_question: "Who are our top 5 customers by revenue?" },
};

export const stageStartedEventFixture: StageStartedEvent = {
  ...baseEvent,
  event_id: "evt-1",
  pipeline_stage: "nlu",
  event_type: "stage_started",
  payload: {},
};

export const stageCompletedEventFixture: StageCompletedEvent = {
  ...baseEvent,
  event_id: "evt-2",
  pipeline_stage: "nlu",
  event_type: "stage_completed",
  payload: { duration_ms: 80 },
};

export const stageFailedEventFixture: StageFailedEvent = {
  ...baseEvent,
  event_id: "evt-3",
  pipeline_stage: "sql_validation",
  event_type: "stage_failed",
  payload: { duration_ms: 12, error_type: "ValidationError", error_message: "Unknown table." },
};

export const pipelineCompletedEventFixture: PipelineCompletedEvent = {
  ...baseEvent,
  event_id: "evt-9",
  pipeline_stage: null,
  event_type: "pipeline_completed",
  payload: { status: "success", error: null, business_answer: businessAnswerFixture },
};

export const tokenPairFixture: TokenPair = {
  access_token: "mock-access-token",
  refresh_token: "mock-refresh-token",
  token_type: "bearer",
};

export const userReadFixture: UserRead = {
  id: 1,
  username: "alice",
  email: "alice@example.com",
  is_active: true,
  is_superuser: false,
  role: "analyst",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

export const adminUserReadFixture: UserRead = {
  ...userReadFixture,
  id: 2,
  username: "admin",
  email: "admin@example.com",
  is_superuser: true,
  role: "admin",
};

export const viewerUserReadFixture: UserRead = {
  ...userReadFixture,
  id: 3,
  username: "viewer",
  email: "viewer@example.com",
  role: "viewer",
};

export const pipelineFailedEventFixture: PipelineFailedEvent = {
  ...baseEvent,
  event_id: "evt-9",
  pipeline_stage: null,
  event_type: "pipeline_failed",
  payload: { error_type: "NluError", error_message: "The question could not be understood." },
};