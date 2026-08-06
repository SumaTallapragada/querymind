import { AlertCircle, CheckCircle2, HelpCircle, RefreshCw, XCircle } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui";
import { LoadingIndicator } from "@/components/LoadingIndicator";
import { useHealth } from "@/hooks/useHealth";
import { errorMessage } from "@/utils/errors";
import type { HealthStatus } from "@/models";

const STATUS_ICON: Record<HealthStatus, typeof CheckCircle2> = {
  healthy: CheckCircle2,
  unhealthy: XCircle,
  unknown: HelpCircle,
};

const STATUS_VARIANT: Record<HealthStatus, "success" | "destructive" | "secondary"> = {
  healthy: "success",
  unhealthy: "destructive",
  unknown: "secondary",
};

export function HealthPage() {
  const { data, isLoading, isError, error, refetch, isFetching, dataUpdatedAt } = useHealth();

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>System health</CardTitle>
          <CardDescription>GET /health</CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
          <RefreshCw className={isFetching ? "animate-spin" : ""} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {isLoading && <LoadingIndicator label="Checking system health..." />}

        {isError && (
          <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            {errorMessage(error)}
          </div>
        )}

        {data && (
          <>
            <div className="flex items-center gap-3">
              <Badge variant={STATUS_VARIANT[data.overall_status]} className="text-sm">
                {data.overall_status.toUpperCase()}
              </Badge>
              {dataUpdatedAt > 0 && (
                <span className="text-xs text-muted-foreground">
                  Last refreshed {new Date(dataUpdatedAt).toLocaleTimeString()}
                </span>
              )}
            </div>

            <ul className="flex flex-col gap-2">
              {data.checks.map((check) => {
                const Icon = STATUS_ICON[check.status];
                return (
                  <li
                    key={check.name}
                    className="flex items-start gap-3 rounded-lg border border-border p-3.5"
                  >
                    <Icon
                      className={
                        check.status === "healthy"
                          ? "mt-0.5 h-5 w-5 shrink-0 text-success"
                          : check.status === "unhealthy"
                            ? "mt-0.5 h-5 w-5 shrink-0 text-destructive"
                            : "mt-0.5 h-5 w-5 shrink-0 text-muted-foreground"
                      }
                      aria-hidden="true"
                    />
                    <div>
                      <p className="font-medium">{check.name.replaceAll("_", " ")}</p>
                      {check.message && <p className="text-sm text-muted-foreground">{check.message}</p>}
                    </div>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
