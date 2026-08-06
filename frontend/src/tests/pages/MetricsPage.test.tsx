import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { MetricsPage } from "@/pages/Metrics";
import { renderWithProviders } from "@/tests/testUtils";
import { metricsSnapshotFixture } from "@/tests/mocks/fixtures";

describe("MetricsPage", () => {
  it("shows the headline stat cards once metrics load", async () => {
    renderWithProviders(<MetricsPage />);

    await waitFor(() =>
      expect(screen.getByText(metricsSnapshotFixture.pipeline_run_count.toLocaleString())).toBeInTheDocument(),
    );
    expect(screen.getByText(metricsSnapshotFixture.sql_execution_count.toLocaleString())).toBeInTheDocument();
  });

  it("renders the chart section titles once metrics load", async () => {
    renderWithProviders(<MetricsPage />);

    await waitFor(() => expect(screen.getByText("Stage latency")).toBeInTheDocument());
    expect(screen.getByText("Pipeline outcomes")).toBeInTheDocument();
    expect(screen.getByText("Repair statistics")).toBeInTheDocument();
    expect(screen.getByText("LLM token usage")).toBeInTheDocument();
    expect(screen.getByText("Cache hit rate")).toBeInTheDocument();
  });
});