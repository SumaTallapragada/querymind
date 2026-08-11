/** Server-state hook for logging in -- a `useMutation` (an action with a side effect, not a
 * cacheable `GET`), the same shape `useQuery.ts#useAskQuestion` uses for `POST /query`. The
 * actual login/token/session logic lives in `store/authStore.ts`; this hook only gives
 * `LoginPage` the `isPending`/`isError`/`error` states TanStack Query already provides instead
 * of hand-rolling them.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";

export function useLogin(): UseMutationResult<void, Error, { username: string; password: string }> {
  const login = useAuthStore((state) => state.login);

  return useMutation<void, Error, { username: string; password: string }>({
    mutationFn: ({ username, password }) => login(username, password),
  });
}