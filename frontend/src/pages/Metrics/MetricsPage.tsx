import { AlertCircle, RefreshCw } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui";
import { LoadingIndicator } from "@/components/LoadingIndicator";
import {
  CacheChart,
  PipelineOutcomeChart,
  RepairStatsChart,
  StageLatencyChart,
  TokenUsageChart,
} from "@/components/MetricsChart";
import { useMetrics } from "@/hooks/useMetrics";
import { errorMessage } from "@/utils/errors";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
    </div>
  );
}

export function MetricsPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useMetrics();

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div>
            <CardTitle>Metrics</CardTitle>
            <CardDescription>GET /health/metrics</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? "animate-spin" : ""} />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading && <LoadingIndicator label="Loading metrics..." />}
          {isError && (
            <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" aria-hidden="true" />
              {errorMessage(error)}
            </div>
          )}
          {data && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="Pipeline runs" value={data.pipeline_run_count.toLocaleString()} />
              <StatCard
                label="Avg. latency"
                value={`${data.average_pipeline_latency_ms.toFixed(0)} ms`}
              />
              <StatCard label="Executions" value={data.sql_execution_count.toLocaleString()} />
              <StatCard label="Rows returned" value={data.total_rows_returned.toLocaleString()} />
            </div>
          )}
        </CardContent>
      </Card>

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Stage latency</CardTitle>
              <CardDescription>Average latency per pipeline stage.</CardDescription>
            </CardHeader>
            <CardContent>
              <StageLatencyChart stageMetrics={data.stage_metrics} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Pipeline outcomes</CardTitle>
              <CardDescription>Success vs. failure count.</CardDescription>
            </CardHeader>
            <CardContent>
              <PipelineOutcomeChart metrics={data} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Repair statistics</CardTitle>
              <CardDescription>Attempted vs. successful repairs.</CardDescription>
            </CardHeader>
            <CardContent>
              <RepairStatsChart metrics={data} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>LLM token usage</CardTitle>
              <CardDescription>Prompt vs. completion tokens.</CardDescription>
            </CardHeader>
            <CardContent>
              <TokenUsageChart metrics={data} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Cache hit rate</CardTitle>
              <CardDescription>Hits vs. misses.</CardDescription>
            </CardHeader>
            <CardContent>
              <CacheChart metrics={data} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
