import { Check, Copy, Download } from "lucide-react";
import { Badge, Button } from "@/components/ui";
import { SqlHighlight } from "./sqlHighlight";
import { useClipboard } from "@/hooks/useClipboard";
import { downloadTextFile } from "@/utils/download";
import type { RepairStatus, SQLRepairResult, SQLValidationResult } from "@/models";

export interface SQLViewerProps {
  sql: string | null;
  validationResult?: SQLValidationResult | null;
  repairResult?: SQLRepairResult | null;
}

const REPAIR_BADGE_VARIANT: Record<RepairStatus, "success" | "warning" | "destructive"> = {
  repaired: "success",
  max_attempts_reached: "warning",
  no_progress: "warning",
  unrepairable: "destructive",
};

const REPAIR_BADGE_LABEL: Record<RepairStatus, string> = {
  repaired: "Repaired",
  max_attempts_reached: "Max attempts reached",
  no_progress: "No progress",
  unrepairable: "Unrepairable",
};

export function SQLViewer({ sql, validationResult, repairResult }: SQLViewerProps) {
  const { copied, copy } = useClipboard();

  if (sql === null) {
    return <p className="text-sm text-muted-foreground">No SQL generated yet.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {validationResult && (
          <Badge variant={validationResult.is_valid ? "success" : "destructive"}>
            {validationResult.is_valid
              ? "Valid"
              : `${validationResult.errors.length} error${validationResult.errors.length === 1 ? "" : "s"}`}
          </Badge>
        )}
        {repairResult && (
          <Badge variant={REPAIR_BADGE_VARIANT[repairResult.status]}>
            {REPAIR_BADGE_LABEL[repairResult.status]}
          </Badge>
        )}
        <div className="ml-auto flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void copy(sql)}
            aria-label="Copy SQL to clipboard"
          >
            {copied ? <Check className="text-success" /> : <Copy />}
            {copied ? "Copied" : "Copy"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => downloadTextFile("query.sql", sql, "text/plain;charset=utf-8")}
            aria-label="Download SQL file"
          >
            <Download />
            Download
          </Button>
        </div>
      </div>
      <pre className="overflow-x-auto rounded-lg border border-border bg-muted/40 p-4">
        <SqlHighlight sql={sql} />
      </pre>
    </div>
  );
}
