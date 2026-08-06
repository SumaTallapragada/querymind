import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { HealthPage } from "@/pages/Health";
import { renderWithProviders } from "@/tests/testUtils";
import { server } from "@/tests/mocks/server";
import { unhealthyHealthReportFixture } from "@/tests/mocks/fixtures";

describe("HealthPage", () => {
  it("shows every health check once loaded, with an overall HEALTHY badge", async () => {
    renderWithProviders(<HealthPage />);

    await waitFor(() => expect(screen.getByText("HEALTHY")).toBeInTheDocument());
    expect(screen.getByText("database")).toBeInTheDocument();
    expect(screen.getByText("llm provider")).toBeInTheDocument();
  });

  it("shows UNHEALTHY and each failing check's message when a check fails", async () => {
    server.use(http.get("/api/v1/health", () => HttpResponse.json(unhealthyHealthReportFixture)));

    renderWithProviders(<HealthPage />);

    await waitFor(() => expect(screen.getByText("UNHEALTHY")).toBeInTheDocument());
    expect(screen.getByText("Connection refused.")).toBeInTheDocument();
  });
});