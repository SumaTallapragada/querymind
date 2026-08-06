/** Server-state hook for the direct, non-streaming `POST /query` call -- a `useMutation` (it's
 * an action with a side effect on the backend, not a cacheable `GET`), updating `queryStore`
 * with the session's lifecycle so `PipelineTimeline`/`SQLViewer`/... render identically to how
 * they render a streamed run's final state.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";
import { askQuestion } from "@/services/api";
import { useQueryStore } from "@/store/queryStore";
import { errorMessage } from "@/utils/errors";
import type { QueryMindResponse } from "@/models";

export function useAskQuestion(): UseMutationResult<QueryMindResponse, Error, string> {
  const beginQuery = useQueryStore((state) => state.beginQuery);
  const setMode = useQueryStore((state) => state.setMode);
  const succeed = useQueryStore((state) => state.succeed);
  const fail = useQueryStore((state) => state.fail);

  return useMutation<QueryMindResponse, Error, string>({
    mutationFn: async (question: string) => {
      setMode("direct");
      beginQuery(question);
      return askQuestion(question);
    },
    onSuccess: (response) => succeed(response),
    onError: (error) => fail(errorMessage(error)),
  });
}
