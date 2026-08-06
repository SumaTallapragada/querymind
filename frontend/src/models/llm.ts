/**
 * Mirrors `querymind.llm.models` (Python). Field names are kept snake_case, exactly matching
 * the JSON every backend endpoint actually sends -- no camelCase transformation layer to keep
 * in sync by hand.
 */

export type LLMProvider = "claude";

export type FinishReason = "complete" | "max_tokens" | "content_filter" | "error";

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
}

export interface GenerationMetrics {
  provider: LLMProvider;
  model: string;
  latency_ms: number;
  token_usage: TokenUsage;
  retry_count: number;
  finish_reason: FinishReason;
}
