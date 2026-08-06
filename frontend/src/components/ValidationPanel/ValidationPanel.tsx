import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui";
import type { SQLValidationResult, ValidationIssue } from "@/models";

export interface ValidationPanelProps {
  validationResult: SQLValidationResult | null;
}

function IssueRow({ issue }: { issue: ValidationIssue }) {
  const isError = issue.severity === "error";
  return (
    <li className="flex items-start gap-2 rounded-md border border-border p-2.5 text-sm">
      {isError ? (
        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
      ) : (
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
      )}
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-xs text-muted-foreground">{issue.code}</span>
        <span>{issue.message}</span>
        {issue.related_object && (
          <span className="text-xs text-muted-foreground">Concerns: {issue.related_object}</span>
        )}
      </div>
    </li>
  );
}

export function ValidationPanel({ validationResult }: ValidationPanelProps) {
  if (validationResult === null) {
    return (
      <p className="text-sm text-muted-foreground">
        No validation result available. Full validation detail is only produced by the direct
        (non-streaming) request mode.
      </p>
    );
  }

  const { is_valid, errors, warnings, validated_tables, validated_columns, validation_statistics } =
    validationResult;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        {is_valid ? (
          <Badge variant="success">
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> Valid
          </Badge>
        ) : (
          <Badge variant="destructive">
            <XCircle className="h-3 w-3" aria-hidden="true" /> Invalid
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">
          {validation_statistics.validation_latency_ms.toFixed(1)} ms &middot;{" "}
          {validation_statistics.table_count} table(s) &middot; {validation_statistics.column_count}{" "}
          column(s)
        </span>
      </div>

      {errors.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Errors ({errors.length})
          </h4>
          <ul className="flex flex-col gap-1.5">
            {errors.map((issue, index) => (
              <IssueRow key={`${issue.code}-${index}`} issue={issue} />
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Warnings ({warnings.length})
          </h4>
          <ul className="flex flex-col gap-1.5">
            {warnings.map((issue, index) => (
              <IssueRow key={`${issue.code}-${index}`} issue={issue} />
            ))}
          </ul>
        </div>
      )}

      {(validated_tables.length > 0 || validated_columns.length > 0) && (
        <div className="flex flex-col gap-1 text-xs text-muted-foreground">
          {validated_tables.length > 0 && <p>Tables: {validated_tables.join(", ")}</p>}
          {validated_columns.length > 0 && <p>Columns: {validated_columns.join(", ")}</p>}
        </div>
      )}
    </div>
  );
}
