import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { getMetrics } from "@/services/api";
import type { MetricsSnapshot } from "@/models";

const REFETCH_INTERVAL_MS = 15_000;

export function useMetrics(): UseQueryResult<MetricsSnapshot, Error> {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: getMetrics,
    refetchInterval: REFETCH_INTERVAL_MS,
  });
}
