import { CheckCircle2, RotateCcw, Trash2, XCircle, Zap } from "lucide-react";
import { Button } from "@/components/ui";
import { useQueryStore } from "@/store/queryStore";
import { useAskQuestion } from "@/hooks/useQuery";
import { useStreaming } from "@/hooks/useStreaming";

function formatLatency(latencyMs: number | null): string {
  if (latencyMs === null) return "";
  return latencyMs < 1000 ? `${latencyMs.toFixed(0)} ms` : `${(latencyMs / 1000).toFixed(2)} s`;
}

export function QueryHistory() {
  const history = useQueryStore((state) => state.history);
  const mode = useQueryStore((state) => state.mode);
  const clearHistory = useQueryStore((state) => state.clearHistory);
  const askQuestion = useAskQuestion();
  const { start } = useStreaming();

  function rerun(question: string): void {
    if (mode === "direct") {
      askQuestion.mutate(question);
    } else {
      start(question);
    }
  }

  if (history.length === 0) {
    return <p className="text-sm text-muted-foreground">No questions asked yet this session.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <Button type="button" variant="ghost" size="sm" onClick={clearHistory}>
          <Trash2 className="h-3.5 w-3.5" />
          Clear
        </Button>
      </div>
      <ul className="flex flex-col gap-1.5">
        {history.map((entry) => (
          <li
            key={entry.id}
            className="flex items-center gap-2 rounded-md border border-border p-2.5 text-sm"
          >
            {entry.status === "success" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <XCircle className="h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate">{entry.question}</p>
              <p className="text-xs text-muted-foreground">
                {new Date(entry.askedAt).toLocaleTimeString()} &middot; {entry.mode}
                {entry.totalLatencyMs !== null && ` · ${formatLatency(entry.totalLatencyMs)}`}
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Ask "${entry.question}" again`}
              onClick={() => rerun(entry.question)}
            >
              {entry.mode === "streaming" ? <Zap className="h-3.5 w-3.5" /> : <RotateCcw className="h-3.5 w-3.5" />}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
