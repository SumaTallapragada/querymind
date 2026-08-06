import { useMemo, useState } from "react";
import { AlertCircle, RefreshCw, Search } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
} from "@/components/ui";
import { DiagnosticsCard } from "@/components/DiagnosticsCard";
import { LoadingIndicator } from "@/components/LoadingIndicator";
import { useDiagnostics } from "@/hooks/useDiagnostics";
import { errorMessage } from "@/utils/errors";
import type { DiagnosticStatus } from "@/models";

const STATUS_FILTERS: Array<{ value: DiagnosticStatus | "all"; label: string }> = [
  { value: "all", label: "All" },
  { value: "pass", label: "Pass" },
  { value: "warning", label: "Warning" },
  { value: "error", label: "Error" },
];

export function DiagnosticsPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useDiagnostics();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<DiagnosticStatus | "all">("all");

  const filteredFindings = useMemo(() => {
    if (!data) return [];
    return data.findings.filter((finding) => {
      const matchesStatus = statusFilter === "all" || finding.status === statusFilter;
      const haystack = `${finding.check_name} ${finding.message} ${finding.details ?? ""}`.toLowerCase();
      const matchesSearch = search.trim() === "" || haystack.includes(search.trim().toLowerCase());
      return matchesStatus && matchesSearch;
    });
  }, [data, search, statusFilter]);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Diagnostics</CardTitle>
            <CardDescription>
              {data ? (
                <>
                  Overall status: <Badge variant={data.overall_status === "pass" ? "success" : data.overall_status === "warning" ? "warning" : "destructive"}>{data.overall_status.toUpperCase()}</Badge>
                </>
              ) : (
                "GET /health/diagnostics"
              )}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? "animate-spin" : ""} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search checks..."
                className="pl-8"
                aria-label="Search diagnostic checks"
              />
            </div>
            <div className="flex gap-1.5" role="group" aria-label="Filter by status">
              {STATUS_FILTERS.map((filter) => (
                <Button
                  key={filter.value}
                  type="button"
                  size="sm"
                  variant={statusFilter === filter.value ? "default" : "outline"}
                  onClick={() => setStatusFilter(filter.value)}
                  aria-pressed={statusFilter === filter.value}
                >
                  {filter.label}
                </Button>
              ))}
            </div>
          </div>

          {isLoading && <LoadingIndicator label="Loading diagnostics..." />}

          {isError && (
            <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errorMessage(error)}
            </div>
          )}

          {data && filteredFindings.length === 0 && (
            <p className="text-sm text-muted-foreground">No checks match your filters.</p>
          )}

          {filteredFindings.length > 0 && (
            <ul className="flex flex-col gap-2">
              {filteredFindings.map((finding) => (
                <DiagnosticsCard key={finding.check_name} finding={finding} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
