import { AlertCircle, CheckCircle2, Clock, XCircle } from "lucide-react";
import { Badge } from "@/components/ui";
import type { ExecutionStatus, SQLExecutionResult } from "@/models";

export interface ExecutionPanelProps {
  executionResult: SQLExecutionResult | null;
}

const STATUS_VARIANT: Record<ExecutionStatus, "success" | "destructive" | "warning"> = {
  success: "success",
  failed: "destructive",
  rejected: "destructive",
  timeout: "warning",
};

const STATUS_ICON: Record<ExecutionStatus, typeof CheckCircle2> = {
  success: CheckCircle2,
  failed: XCircle,
  rejected: XCircle,
  timeout: Clock,
};

export function ExecutionPanel({ executionResult }: ExecutionPanelProps) {
  if (executionResult === null) {
    return <p className="text-sm text-muted-foreground">No execution has run yet.</p>;
  }

  const { status, statistics, execution_error } = executionResult;
  const Icon = STATUS_ICON[status];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Badge variant={STATUS_VARIANT[status]}>
          <Icon className="h-3 w-3" aria-hidden="true" /> {status}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {statistics.execution_latency_ms.toFixed(0)} ms &middot; {statistics.rows_returned} row(s)
          &middot; {statistics.columns_returned} column(s)
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted-foreground">Database</dt>
          <dd>{statistics.database_name}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Dialect</dt>
          <dd className="capitalize">{statistics.dialect}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Latency</dt>
          <dd>{statistics.execution_latency_ms.toFixed(1)} ms</dd>
        </div>
      </dl>

      {execution_error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
          <div>
            <p className="font-mono text-xs text-muted-foreground">{execution_error.code}</p>
            <p>{execution_error.message}</p>
          </div>
        </div>
      )}
    </div>
  );
}
