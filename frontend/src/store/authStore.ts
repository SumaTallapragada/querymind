/**
 * Client-side session state for `/auth/*`. Deliberately splits what's persisted from what
 * isn't: the backend has no HttpOnly-cookie option (see `services/api.ts`'s own docstring on
 * token storage), so a refresh token has to live somewhere on the client to survive a reload --
 * `zustand/persist`'s `partialize` keeps that to *only* `refreshToken` (localStorage). The
 * short-lived access token and the user profile stay in memory only, rebuilt on startup by
 * `restoreSession` exchanging the persisted refresh token for a fresh pair. This is the one
 * place `login`/`logout`/session-restoration business logic lives -- components and
 * `services/api.ts`'s request interceptor both read/drive this store rather than duplicating
 * any of it.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  getCurrentUser,
  login as loginRequest,
  logoutRequest,
  refreshTokenPair,
} from "@/services/api";
import { errorMessage } from "@/utils/errors";
import type { TokenPair, UserRead } from "@/models";

export type AuthStatus = "idle" | "authenticating" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  accessToken: string | null;
  refreshToken: string | null;
  user: UserRead | null;
  error: string | null;

  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  restoreSession: () => Promise<void>;
  setTokens: (tokens: TokenPair) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      status: "idle",
      accessToken: null,
      refreshToken: null,
      user: null,
      error: null,

      setTokens: (tokens) =>
        set({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token }),

      clear: () =>
        set({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null }),

      login: async (username, password) => {
        set({ status: "authenticating", error: null });
        try {
          const tokens = await loginRequest(username, password);
          get().setTokens(tokens);
          const user = await getCurrentUser();
          set({ status: "authenticated", user, error: null });
        } catch (error) {
          set({
            status: "unauthenticated",
            accessToken: null,
            refreshToken: null,
            user: null,
            error: errorMessage(error),
          });
          throw error;
        }
      },

      logout: async () => {
        const refreshToken = get().refreshToken;
        set({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null, error: null });
        if (!refreshToken) return;
        try {
          await logoutRequest(refreshToken);
        } catch {
          // Best-effort: the client-side session is already cleared regardless of whether the
          // server-side revocation call succeeds (e.g. the refresh token already expired).
        }
      },

      restoreSession: async () => {
        const refreshToken = get().refreshToken;
        if (!refreshToken) {
          set({ status: "unauthenticated" });
          return;
        }
        set({ status: "authenticating" });
        try {
          const tokens = await refreshTokenPair(refreshToken);
          get().setTokens(tokens);
          const user = await getCurrentUser();
          set({ status: "authenticated", user, error: null });
        } catch {
          set({ status: "unauthenticated", accessToken: null, refreshToken: null, user: null });
        }
      },
    }),
    {
      name: "querymind-auth",
      partialize: (state) => ({ refreshToken: state.refreshToken }),
    },
  ),
);