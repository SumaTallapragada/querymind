import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useSettings } from "@/hooks/useSettings";
import { renderHookWithProviders } from "@/tests/testUtils";
import { server } from "@/tests/mocks/server";
import { settingsResponseFixture } from "@/tests/mocks/fixtures";

describe("useSettings", () => {
  it("resolves GET /settings into SettingsResponse", async () => {
    const { result } = renderHookWithProviders(() => useSettings());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(settingsResponseFixture);
  });

  it("surfaces a backend error via isError", async () => {
    server.use(
      http.get("/api/v1/settings", () =>
        HttpResponse.json({ detail: "boom", error_type: "InternalError" }, { status: 500 }),
      ),
    );

    const { result } = renderHookWithProviders(() => useSettings());

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});