import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { getDiagnostics } from "@/services/api";
import type { DiagnosticsReport } from "@/models";

export function useDiagnostics(): UseQueryResult<DiagnosticsReport, Error> {
  return useQuery({
    queryKey: ["diagnostics"],
    queryFn: getDiagnostics,
  });
}
