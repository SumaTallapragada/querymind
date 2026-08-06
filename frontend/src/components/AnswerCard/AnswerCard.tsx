import { Hash, Table2 } from "lucide-react";
import { Badge } from "@/components/ui";
import type { AnswerType, BusinessAnswer } from "@/models";

export interface AnswerCardProps {
  businessAnswer: BusinessAnswer | null;
}

const ANSWER_TYPE_LABEL: Record<AnswerType, string> = {
  scalar: "Scalar",
  table: "Table",
  empty_result: "Empty result",
  aggregation: "Aggregation",
  detail: "Detail",
};

export function AnswerCard({ businessAnswer }: AnswerCardProps) {
  if (businessAnswer === null) {
    return <p className="text-sm text-muted-foreground">No answer yet -- ask a question above.</p>;
  }

  const { answer_type, summary, statistics } = businessAnswer;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Badge variant="secondary">{ANSWER_TYPE_LABEL[answer_type]}</Badge>
        {summary.contains_numeric && (
          <Hash className="h-3.5 w-3.5 text-muted-foreground" aria-label="Contains numeric data" />
        )}
        {answer_type === "table" && (
          <Table2 className="h-3.5 w-3.5 text-muted-foreground" aria-label="Tabular result" />
        )}
      </div>
      <h3 className="text-lg font-semibold tracking-tight">{summary.title}</h3>
      <p className="text-sm text-muted-foreground">{summary.description}</p>
      <p className="text-xs text-muted-foreground">
        Formatted in {statistics.formatting_latency_ms.toFixed(1)} ms
      </p>
    </div>
  );
}
