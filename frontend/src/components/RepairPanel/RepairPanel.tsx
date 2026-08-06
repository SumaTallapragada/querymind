import { CheckCircle2, XCircle } from "lucide-react";
import { Badge } from "@/components/ui";
import type { RepairAttempt, RepairStatus, SQLRepairResult } from "@/models";

export interface RepairPanelProps {
  repairResult: SQLRepairResult | null;
}

const STATUS_VARIANT: Record<RepairStatus, "success" | "warning" | "destructive"> = {
  repaired: "success",
  max_attempts_reached: "warning",
  no_progress: "warning",
  unrepairable: "destructive",
};

const STATUS_LABEL: Record<RepairStatus, string> = {
  repaired: "Repaired",
  max_attempts_reached: "Max attempts reached",
  no_progress: "No progress",
  unrepairable: "Unrepairable",
};

function AttemptRow({ attempt }: { attempt: RepairAttempt }) {
  return (
    <li className="flex flex-col gap-1 rounded-md border border-border p-2.5 text-sm">
      <div className="flex items-center gap-2">
        {attempt.success ? (
          <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
        ) : (
          <XCircle className="h-4 w-4 text-destructive" aria-hidden="true" />
        )}
        <span className="font-medium">Attempt {attempt.attempt_number}</span>
        <span className="text-xs text-muted-foreground">{attempt.repair_reason.replaceAll("_", " ")}</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {attempt.validation_result.is_valid
          ? "Repaired SQL validated successfully."
          : `Still ${attempt.validation_result.errors.length} error(s) after this attempt.`}
      </p>
    </li>
  );
}

export function RepairPanel({ repairResult }: RepairPanelProps) {
  if (repairResult === null) {
    return (
      <p className="text-sm text-muted-foreground">
        Repair never ran for this question -- the generated SQL validated successfully on the
        first attempt.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Badge variant={STATUS_VARIANT[repairResult.status]}>{STATUS_LABEL[repairResult.status]}</Badge>
        <span className="text-xs text-muted-foreground">
          {repairResult.statistics.attempt_count} attempt(s) &middot;{" "}
          {repairResult.statistics.repair_latency_ms.toFixed(0)} ms
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {repairResult.history.attempts.map((attempt) => (
          <AttemptRow key={attempt.attempt_number} attempt={attempt} />
        ))}
      </ul>
    </div>
  );
}
