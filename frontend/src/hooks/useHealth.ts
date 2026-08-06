import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { getHealth } from "@/services/api";
import type { HealthReport } from "@/models";

const REFETCH_INTERVAL_MS = 30_000;

export function useHealth(): UseQueryResult<HealthReport, Error> {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: REFETCH_INTERVAL_MS,
  });
}
