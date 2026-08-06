import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { getSettings } from "@/services/api";
import type { SettingsResponse } from "@/models";

export function useSettings(): UseQueryResult<SettingsResponse, Error> {
  return useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    staleTime: Infinity,
  });
}
