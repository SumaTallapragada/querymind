/** MSW request handlers for every `services/api.ts` call, matched against `API_BASE_URL`
 * ("/api/v1" by default -- see `services/api.ts`). Tests that need a non-default response
 * (an error, an empty result, ...) override a handler per-test with `server.use(...)`.
 */

import { http, HttpResponse } from "msw";
import {
  businessAnswerFixture,
  diagnosticsReportFixture,
  generatedSqlFixture,
  healthReportFixture,
  metricsSnapshotFixture,
  queryMindResponseFixture,
  settingsResponseFixture,
  sqlExecutionResultFixture,
  sqlRepairResultFixture,
  sqlValidationResultFixture,
  tokenPairFixture,
  userReadFixture,
} from "./fixtures";

const BASE = "/api/v1";

export const handlers = [
  http.post(`${BASE}/query`, () => HttpResponse.json(queryMindResponseFixture)),

  http.post(`${BASE}/query/sql`, () =>
    HttpResponse.json({
      original_question: queryMindResponseFixture.original_question,
      generated_sql: generatedSqlFixture,
      validation_result: sqlValidationResultFixture,
      repair_result: null,
      statistics: queryMindResponseFixture.statistics,
    }),
  ),

  http.post(`${BASE}/query/validate`, () => HttpResponse.json(sqlValidationResultFixture)),

  http.post(`${BASE}/query/repair`, () => HttpResponse.json(sqlRepairResultFixture)),

  http.post(`${BASE}/query/execute`, () => HttpResponse.json(sqlExecutionResultFixture)),

  http.post(`${BASE}/query/format`, () => HttpResponse.json(businessAnswerFixture)),

  http.get(`${BASE}/health`, () => HttpResponse.json(healthReportFixture)),

  http.get(`${BASE}/health/live`, () => HttpResponse.json({ status: "ok" })),

  http.get(`${BASE}/health/diagnostics`, () => HttpResponse.json(diagnosticsReportFixture)),

  http.get(`${BASE}/health/metrics`, () => HttpResponse.json(metricsSnapshotFixture)),

  http.get(`${BASE}/settings`, () => HttpResponse.json(settingsResponseFixture)),

  http.post(`${BASE}/auth/login`, () => HttpResponse.json(tokenPairFixture)),

  http.post(`${BASE}/auth/refresh`, () => HttpResponse.json(tokenPairFixture)),

  http.post(`${BASE}/auth/logout`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${BASE}/auth/me`, () => HttpResponse.json(userReadFixture)),
];