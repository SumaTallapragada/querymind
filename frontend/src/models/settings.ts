/** Mirrors `querymind.api.models.response.SettingsResponse`. Read-only, never a secret. */

export interface SettingsResponse {
  app_name: string;
  version: string;
  environment: string;
  api_v1_prefix: string;
  database_engine: string;
  database_name: string;
  llm_provider: string;
  llm_model: string;
  streaming_transports: string[];
}
