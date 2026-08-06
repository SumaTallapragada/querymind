import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MetricsSnapshot } from "@/models";

export interface TokenUsageChartProps {
  metrics: Pick<MetricsSnapshot, "llm_prompt_tokens" | "llm_completion_tokens">;
}

/** Prompt vs. completion token counts, from `MetricsSnapshot`. */
export function TokenUsageChart({ metrics }: TokenUsageChartProps) {
  const data = [
    { name: "Prompt", tokens: metrics.llm_prompt_tokens },
    { name: "Completion", tokens: metrics.llm_completion_tokens },
  ];

  if (metrics.llm_prompt_tokens === 0 && metrics.llm_completion_tokens === 0) {
    return <p className="text-sm text-muted-foreground">No LLM token usage recorded yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="var(--color-muted-foreground)" />
        <YAxis tick={{ fontSize: 12 }} stroke="var(--color-muted-foreground)" />
        <Tooltip
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Bar dataKey="tokens" fill="var(--color-primary)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
