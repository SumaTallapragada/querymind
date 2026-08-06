import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui";
import type { DiagnosticFinding, DiagnosticStatus } from "@/models";

export interface DiagnosticsCardProps {
  finding: DiagnosticFinding;
}

const STATUS_ICON: Record<DiagnosticStatus, typeof CheckCircle2> = {
  pass: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const STATUS_VARIANT: Record<DiagnosticStatus, "success" | "warning" | "destructive"> = {
  pass: "success",
  warning: "warning",
  error: "destructive",
};

export function DiagnosticsCard({ finding }: DiagnosticsCardProps) {
  const Icon = STATUS_ICON[finding.status];
  return (
    <li className="flex items-start gap-3 rounded-lg border border-border p-3.5">
      <Icon
        className={
          finding.status === "pass"
            ? "mt-0.5 h-5 w-5 shrink-0 text-success"
            : finding.status === "warning"
              ? "mt-0.5 h-5 w-5 shrink-0 text-warning"
              : "mt-0.5 h-5 w-5 shrink-0 text-destructive"
        }
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">{finding.check_name.replaceAll("_", " ")}</p>
          <Badge variant={STATUS_VARIANT[finding.status]}>{finding.status.toUpperCase()}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{finding.message}</p>
        {finding.details && (
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{finding.details}</p>
        )}
      </div>
    </li>
  );
}
