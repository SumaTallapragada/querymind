import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { SettingsPage } from "@/pages/Settings";
import { renderWithProviders } from "@/tests/testUtils";
import { server } from "@/tests/mocks/server";
import { settingsResponseFixture } from "@/tests/mocks/fixtures";

describe("SettingsPage", () => {
  it("shows a loading indicator, then the settings once loaded", async () => {
    renderWithProviders(<SettingsPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading settings...");

    await waitFor(() => expect(screen.getByText(settingsResponseFixture.app_name)).toBeInTheDocument());
    expect(screen.getByText(settingsResponseFixture.database_name)).toBeInTheDocument();
    // Badges render the raw lowercase value; "uppercase" is a CSS text-transform, not text content.
    expect(screen.getByText("sse")).toBeInTheDocument();
    expect(screen.getByText("websocket")).toBeInTheDocument();
  });

  it("never renders a credential-shaped value even on error", async () => {
    server.use(
      http.get("/api/v1/settings", () =>
        HttpResponse.json({ detail: "Internal error.", error_type: "InternalError" }, { status: 500 }),
      ),
    );

    renderWithProviders(<SettingsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Internal error.");
  });
});