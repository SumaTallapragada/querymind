import { beforeEach, describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { useAuthStore } from "@/store/authStore";
import { server } from "@/tests/mocks/server";
import { tokenPairFixture, userReadFixture } from "@/tests/mocks/fixtures";

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

describe("useAuthStore.login", () => {
  it("on success, sets both tokens, fetches the current user, and marks authenticated", async () => {
    await useAuthStore.getState().login("alice", "correct-password");

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.accessToken).toBe(tokenPairFixture.access_token);
    expect(state.refreshToken).toBe(tokenPairFixture.refresh_token);
    expect(state.user).toEqual(userReadFixture);
    expect(state.error).toBeNull();
  });

  it("on failure, clears tokens/user, records a safe error message, and rethrows", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { detail: "Incorrect username or password.", error_type: "InvalidCredentialsError" },
          { status: 401 },
        ),
      ),
    );

    await expect(useAuthStore.getState().login("alice", "wrong-password")).rejects.toThrow();

    const state = useAuthStore.getState();
    expect(state.status).toBe("unauthenticated");
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.error).toBe("Incorrect username or password.");
  });
});

describe("useAuthStore.logout", () => {
  it("clears the session immediately, best-effort revoking the refresh token server-side", async () => {
    useAuthStore.setState({
      status: "authenticated",
      accessToken: "a",
      refreshToken: "r",
      user: userReadFixture,
    });

    await useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.status).toBe("unauthenticated");
    expect(state.accessToken).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
  });

  it("still clears local state even when the server-side revoke call fails", async () => {
    server.use(
      http.post("/api/v1/auth/logout", () =>
        HttpResponse.json({ detail: "Internal error.", error_type: "InternalError" }, { status: 500 }),
      ),
    );
    useAuthStore.setState({
      status: "authenticated",
      accessToken: "a",
      refreshToken: "r",
      user: userReadFixture,
    });

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });

  it("is a no-op HTTP-wise when there is no refresh token to revoke", async () => {
    let logoutCallCount = 0;
    server.use(
      http.post("/api/v1/auth/logout", () => {
        logoutCallCount += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await useAuthStore.getState().logout();

    expect(logoutCallCount).toBe(0);
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });
});

describe("useAuthStore.restoreSession", () => {
  it("with no persisted refresh token, goes straight to unauthenticated", async () => {
    await useAuthStore.getState().restoreSession();

    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });

  it("with a persisted refresh token, restores a full session", async () => {
    useAuthStore.setState({ refreshToken: "persisted-refresh-token" });

    await useAuthStore.getState().restoreSession();

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.user).toEqual(userReadFixture);
    expect(state.accessToken).toBe(tokenPairFixture.access_token);
  });

  it("clears state when the persisted refresh token is rejected", async () => {
    server.use(
      http.post("/api/v1/auth/refresh", () =>
        HttpResponse.json({ detail: "The token has expired.", error_type: "TokenExpiredError" }, { status: 401 }),
      ),
    );
    useAuthStore.setState({ refreshToken: "expired-refresh-token" });

    await useAuthStore.getState().restoreSession();

    const state = useAuthStore.getState();
    expect(state.status).toBe("unauthenticated");
    expect(state.refreshToken).toBeNull();
    expect(state.accessToken).toBeNull();
  });
});