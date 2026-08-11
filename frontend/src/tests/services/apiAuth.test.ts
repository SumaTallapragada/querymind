/** Covers the token-attachment / refresh-and-retry behavior centralized in `services/api.ts`'s
 * `request()` -- see that file's module docstring. `getSettings` (an existing, already-mocked
 * `ADMIN`-only endpoint) stands in for "any authenticated call"; nothing here is specific to
 * settings itself.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { getSettings, login, logoutRequest } from "@/services/api";
import { useAuthStore } from "@/store/authStore";
import { server } from "@/tests/mocks/server";
import { settingsResponseFixture, tokenPairFixture, userReadFixture } from "@/tests/mocks/fixtures";
import { ApiError } from "@/models";

const INITIAL_STATE = {
  status: "idle" as const,
  accessToken: null,
  refreshToken: null,
  user: null,
  error: null,
};

beforeEach(() => {
  useAuthStore.setState(INITIAL_STATE);
});

describe("request() Authorization header", () => {
  it("attaches 'Bearer <accessToken>' when authenticated", async () => {
    useAuthStore.setState({ accessToken: "test-access-token" });
    let receivedAuth: string | null = "unset";
    server.use(
      http.get("/api/v1/settings", ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return HttpResponse.json(settingsResponseFixture);
      }),
    );

    await getSettings();

    expect(receivedAuth).toBe("Bearer test-access-token");
  });

  it("omits the header when there is no access token", async () => {
    let receivedAuth: string | null = "unset";
    server.use(
      http.get("/api/v1/settings", ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return HttpResponse.json(settingsResponseFixture);
      }),
    );

    await getSettings();

    expect(receivedAuth).toBeNull();
  });

  it("never attaches a header to /auth/login (no token exists yet)", async () => {
    useAuthStore.setState({ accessToken: "stale-token-from-a-previous-session" });
    let receivedAuth: string | null = "unset";
    server.use(
      http.post("/api/v1/auth/login", ({ request }) => {
        receivedAuth = request.headers.get("Authorization");
        return HttpResponse.json(tokenPairFixture);
      }),
    );

    await login("alice", "correct-password");

    expect(receivedAuth).toBeNull();
  });
});

describe("request() 401 refresh-and-retry", () => {
  it("refreshes once and retries the original request on a 401", async () => {
    useAuthStore.setState({ accessToken: "expired-token", refreshToken: "good-refresh-token" });

    let settingsCallCount = 0;
    let refreshCallCount = 0;
    server.use(
      http.get("/api/v1/settings", ({ request }) => {
        settingsCallCount += 1;
        if (request.headers.get("Authorization") === "Bearer expired-token") {
          return HttpResponse.json({ detail: "The token has expired.", error_type: "TokenExpiredError" }, { status: 401 });
        }
        return HttpResponse.json(settingsResponseFixture);
      }),
      http.post("/api/v1/auth/refresh", () => {
        refreshCallCount += 1;
        return HttpResponse.json(tokenPairFixture);
      }),
    );

    const result = await getSettings();

    expect(result).toEqual(settingsResponseFixture);
    expect(refreshCallCount).toBe(1);
    expect(settingsCallCount).toBe(2);
    expect(useAuthStore.getState().accessToken).toBe(tokenPairFixture.access_token);
  });

  it("shares a single in-flight refresh across concurrent 401s (no duplicate refresh calls)", async () => {
    useAuthStore.setState({ accessToken: "expired-token", refreshToken: "good-refresh-token" });

    let refreshCallCount = 0;
    server.use(
      http.get("/api/v1/settings", ({ request }) => {
        if (request.headers.get("Authorization") === "Bearer expired-token") {
          return HttpResponse.json({ detail: "The token has expired.", error_type: "TokenExpiredError" }, { status: 401 });
        }
        return HttpResponse.json(settingsResponseFixture);
      }),
      http.post("/api/v1/auth/refresh", async () => {
        refreshCallCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 20));
        return HttpResponse.json(tokenPairFixture);
      }),
    );

    const results = await Promise.all([getSettings(), getSettings(), getSettings()]);

    expect(results).toEqual([settingsResponseFixture, settingsResponseFixture, settingsResponseFixture]);
    expect(refreshCallCount).toBe(1);
  });

  it("clears the auth store and does not retry again when the refresh token itself is rejected", async () => {
    useAuthStore.setState({
      status: "authenticated",
      accessToken: "expired-token",
      refreshToken: "dead-refresh-token",
      user: userReadFixture,
    });

    let settingsCallCount = 0;
    let refreshCallCount = 0;
    server.use(
      http.get("/api/v1/settings", () => {
        settingsCallCount += 1;
        return HttpResponse.json({ detail: "The token has expired.", error_type: "TokenExpiredError" }, { status: 401 });
      }),
      http.post("/api/v1/auth/refresh", () => {
        refreshCallCount += 1;
        return HttpResponse.json({ detail: "Invalid token.", error_type: "InvalidTokenError" }, { status: 401 });
      }),
    );

    await expect(getSettings()).rejects.toThrow(ApiError);

    // Exactly one refresh attempt, exactly one settings attempt: no infinite refresh/retry loop.
    expect(refreshCallCount).toBe(1);
    expect(settingsCallCount).toBe(1);
    expect(useAuthStore.getState().status).toBe("unauthenticated");
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("never retries /auth/refresh itself on a 401 (would recurse forever otherwise)", async () => {
    useAuthStore.setState({ refreshToken: "dead-refresh-token" });

    let refreshCallCount = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshCallCount += 1;
        return HttpResponse.json({ detail: "Invalid token.", error_type: "InvalidTokenError" }, { status: 401 });
      }),
    );

    await expect(useAuthStore.getState().restoreSession()).resolves.toBeUndefined();

    expect(refreshCallCount).toBe(1);
  });
});

describe("logoutRequest", () => {
  it("resolves without attempting to parse the 204's empty body", async () => {
    await expect(logoutRequest("some-refresh-token")).resolves.toBeUndefined();
  });
});