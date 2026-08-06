import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { useDiagnostics } from "@/hooks/useDiagnostics";
import { useHealth } from "@/hooks/useHealth";
import { useMetrics } from "@/hooks/useMetrics";
import { renderHookWithProviders } from "@/tests/testUtils";
import { diagnosticsReportFixture, healthReportFixture, metricsSnapshotFixture } from "@/tests/mocks/fixtures";

describe("useHealth", () => {
  it("resolves GET /health into a HealthReport", async () => {
    const { result } = renderHookWithProviders(() => useHealth());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(healthReportFixture);
  });
});

describe("useMetrics", () => {
  it("resolves GET /health/metrics into a MetricsSnapshot", async () => {
    const { result } = renderHookWithProviders(() => useMetrics());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(metricsSnapshotFixture);
  });
});

describe("useDiagnostics", () => {
  it("resolves GET /health/diagnostics into a DiagnosticsReport", async () => {
    const { result } = renderHookWithProviders(() => useDiagnostics());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(diagnosticsReportFixture);
  });
});